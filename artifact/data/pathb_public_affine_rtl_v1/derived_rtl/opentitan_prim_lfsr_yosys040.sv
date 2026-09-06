// Copyright lowRISC contributors (OpenTitan project).
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
//
// This module implements different LFSR types:
//
// 0) Galois XOR type LFSR ([1], internal XOR gates, very fast).
//    Parameterizable width from 3 to 168 bits.
//    Coefficients obtained from [3].
//
// 1) Fibonacci XNOR type LFSR, parameterizable from 3 to 168 bits.
//    Coefficients obtained from [3].
//
// All flavors have an additional entropy input and lockup protection, which
// reseeds the state once it has accidentally fallen into the all-zero (XOR) or
// all-one (XNOR) state. Further, an external seed can be loaded into the LFSR
// state at runtime. If that seed is all-zero (XOR case) or all-one (XNOR case),
// the state will be reseeded in the next cycle using the lockup protection mechanism.
// Note that the external seed input takes precedence over internal state updates.
//
// All polynomials up to 34 bit in length have been verified in simulation.
//
// Refs: [1] https://en.wikipedia.org/wiki/Linear-feedback_shift_register
//       [2] https://users.ece.cmu.edu/~koopman/lfsr/
//       [3] https://www.xilinx.com/support/documentation/application_notes/xapp052.pdf

`include "prim_assert.sv"

module prim_lfsr #(
  // Lfsr Type, can be FIB_XNOR or GAL_XOR
  parameter                    LfsrType     = "GAL_XOR",
  // Lfsr width
  parameter int unsigned       LfsrDw       = 32,
  // Derived parameter, do not override
  localparam int unsigned      LfsrIdxDw    = $clog2(LfsrDw),
  // Width of the entropy input to be XOR'd into state (lfsr_q[EntropyDw-1:0])
  parameter int unsigned       EntropyDw    =  8,
  // Width of output tap (from lfsr_q[StateOutDw-1:0])
  parameter int unsigned       StateOutDw   =  8,
  // Lfsr reset state, must be nonzero!
  parameter logic [LfsrDw-1:0] DefaultSeed  = LfsrDw'(1),
  // Custom polynomial coeffs
  parameter logic [LfsrDw-1:0] CustomCoeffs = '0,
  // If StatePermEn is set to 1, the custom permutation specified via StatePerm is applied to the
  // state output, in order to break linear shifting patterns of the LFSR. Note that this
  // permutation represents a way of customizing the LFSR via a random netlist constant. This is
  // different from the NonLinearOut feature below which just transforms the output non-linearly
  // with a fixed function. In most cases, designers should consider enabling StatePermEn as it
  // comes basically "for free" in terms of area and timing impact. NonLinearOut on the other hand
  // has area and timing implications and designers should consider whether the use of that feature
  // is justified.
  parameter bit                StatePermEn  = 1'b0,
  parameter logic [LfsrDw*LfsrIdxDw-1:0] StatePerm = '0,
  // Enable this for DV, disable this for long LFSRs in FPV
  parameter bit                MaxLenSVA    = 1'b1,
  // Can be disabled in cases where seed and entropy
  // inputs are unused in order to not distort coverage
  // (the SVA will be unreachable in such cases)
  parameter bit                LockupSVA    = 1'b1,
  parameter bit                ExtSeedSVA   = 1'b1,
  // Introduce non-linearity to lfsr output. Note, unlike StatePermEn, this feature is not "for
  // free". Please double check that this feature is indeed required. Also note that this feature
  // is only available for LFSRs that have a power-of-two width greater or equal 16bit.
  parameter bit                NonLinearOut = 1'b0
) (
  input                         clk_i,
  input                         rst_ni,
  input                         seed_en_i, // load external seed into the state (takes precedence)
  input        [LfsrDw-1:0]     seed_i,    // external seed input
  input                         lfsr_en_i, // enables the LFSR
  input        [EntropyDw-1:0]  entropy_i, // additional entropy to be XOR'ed into the state
  output logic [StateOutDw-1:0] state_o    // (partial) LFSR state output
);

  // automatically generated with util/design/get-lfsr-coeffs.py script
  localparam int unsigned LUT_OFF = 3;
  wire [167:0] LFSR_COEFFS [0:165];

  logic lockup;
  logic [LfsrDw-1:0] lfsr_d, lfsr_q;
  logic [LfsrDw-1:0] next_lfsr_state, coeffs;

  // Enable the randomization of DefaultSeed using DefaultSeedLocal in DV simulations.
  `ifdef SIMULATION
  `ifdef VERILATOR
      localparam logic [LfsrDw-1:0] DefaultSeedLocal = DefaultSeed;

  `else
    logic [LfsrDw-1:0] DefaultSeedLocal;
    logic prim_lfsr_use_default_seed;

    initial begin : p_randomize_default_seed
      if (!$value$plusargs("prim_lfsr_use_default_seed=%0d", prim_lfsr_use_default_seed)) begin
        // 30% of the time, use the DefaultSeed parameter; 70% of the time, randomize it.
        `ASSERT_I(UseDefaultSeedRandomizeCheck_A, std::randomize(prim_lfsr_use_default_seed) with {
                                                  prim_lfsr_use_default_seed dist {0:/7, 1:/3};})
      end
      if (prim_lfsr_use_default_seed) begin
        DefaultSeedLocal = DefaultSeed;
      end else begin
        // Randomize the DefaultSeedLocal ensuring its not all 0s or all 1s.
        `ASSERT_I(DefaultSeedLocalRandomizeCheck_A, std::randomize(DefaultSeedLocal) with {
                                                    !(DefaultSeedLocal inside {'0, '1});})
      end
      $display("%m: DefaultSeed = 0x%0h, DefaultSeedLocal = 0x%0h", DefaultSeed, DefaultSeedLocal);
    end
  `endif  // ifdef VERILATOR

  `else
    localparam logic [LfsrDw-1:0] DefaultSeedLocal = DefaultSeed;

  `endif  // ifdef SIMULATION

  ////////////////
  // Galois XOR //
  ////////////////
  if (64'(LfsrType) == 64'("GAL_XOR")) begin : gen_gal_xor

    // if custom polynomial is provided
    if (CustomCoeffs > 0) begin : gen_custom
      assign coeffs = CustomCoeffs[LfsrDw-1:0];
    end else begin : gen_lut
      assign coeffs = LFSR_COEFFS[LfsrDw-LUT_OFF][LfsrDw-1:0];
      // check that the most significant bit of polynomial is 1
      `ASSERT_INIT(MinLfsrWidth_A, LfsrDw >= $low(LFSR_COEFFS)+LUT_OFF)
      `ASSERT_INIT(MaxLfsrWidth_A, LfsrDw <= $high(LFSR_COEFFS)+LUT_OFF)
    end

    // calculate next state using internal XOR feedback and entropy input
    assign next_lfsr_state = LfsrDw'(entropy_i) ^ ({LfsrDw{lfsr_q[0]}} & coeffs) ^ (lfsr_q >> 1);

    // lockup condition is all-zero
    assign lockup = ~(|lfsr_q);

    // check that seed is not all-zero
    `ASSERT_INIT(DefaultSeedNzCheck_A, |DefaultSeedLocal)


  ////////////////////
  // Fibonacci XNOR //
  ////////////////////
  end else if (64'(LfsrType) == "FIB_XNOR") begin : gen_fib_xnor

    // if custom polynomial is provided
    if (CustomCoeffs > 0) begin : gen_custom
      assign coeffs = CustomCoeffs[LfsrDw-1:0];
    end else begin : gen_lut
      assign coeffs = LFSR_COEFFS[LfsrDw-LUT_OFF][LfsrDw-1:0];
      // check that the most significant bit of polynomial is 1
      `ASSERT_INIT(MinLfsrWidth_A, LfsrDw >= $low(LFSR_COEFFS)+LUT_OFF)
      `ASSERT_INIT(MaxLfsrWidth_A, LfsrDw <= $high(LFSR_COEFFS)+LUT_OFF)
    end

    // calculate next state using external XNOR feedback and entropy input
    assign next_lfsr_state = LfsrDw'(entropy_i) ^ {lfsr_q[LfsrDw-2:0], ~(^(lfsr_q & coeffs))};

    // lockup condition is all-ones
    assign lockup = &lfsr_q;

    // check that seed is not all-ones
    `ASSERT_INIT(DefaultSeedNzCheck_A, !(&DefaultSeedLocal))


  /////////////
  // Unknown //
  /////////////
  end else begin : gen_unknown_type
    assign coeffs = '0;
    assign next_lfsr_state = '0;
    assign lockup = 1'b0;
    `ASSERT_INIT(UnknownLfsrType_A, 0)
  end


  //////////////////
  // Shared logic //
  //////////////////

  assign lfsr_d = (seed_en_i)           ? seed_i          :
                  (lfsr_en_i && lockup) ? DefaultSeedLocal     :
                  (lfsr_en_i)           ? next_lfsr_state :
                                          lfsr_q;

  // Specialization of the upstream NonLinearOut=0 and StatePermEn=0 branches.
  logic [LfsrDw-1:0] sbox_out;
  assign sbox_out = lfsr_q;
  assign state_o = StateOutDw'(sbox_out);

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_reg
    if (!rst_ni) begin
      lfsr_q <= DefaultSeedLocal;
    end else begin
      lfsr_q <= lfsr_d;
    end
  end


  ///////////////////////
  // shared assertions //
  ///////////////////////

  `ASSERT_KNOWN(DataKnownO_A, state_o)

// the code below is not meant to be synthesized,
// but it is intended to be used in simulation and FPV
`ifndef SYNTHESIS
  function automatic logic [LfsrDw-1:0] compute_next_state(logic [LfsrDw-1:0]    lfsrcoeffs,
                                                           logic [EntropyDw-1:0] entropy,
                                                           logic [LfsrDw-1:0]    current_state);
    logic state0;
    logic [LfsrDw-1:0] next_state;

    next_state = current_state;

    // Galois XOR
    if (64'(LfsrType) == 64'("GAL_XOR")) begin
      if (next_state == 0) begin
        next_state = DefaultSeedLocal;
      end else begin
        state0 = next_state[0];
        next_state = next_state >> 1;
        if (state0) next_state ^= lfsrcoeffs;
        next_state ^= LfsrDw'(entropy);
      end
    // Fibonacci XNOR
    end else if (64'(LfsrType) == "FIB_XNOR") begin
      if (&next_state) begin
        next_state = DefaultSeedLocal;
      end else begin
        state0 = ~(^(next_state & lfsrcoeffs));
        next_state = next_state << 1;
        next_state[0] = state0;
        next_state ^= LfsrDw'(entropy);
      end
    end else begin
      $error("unknown lfsr type");
    end

    return next_state;
  endfunction : compute_next_state

  // check whether next state is computed correctly
  // we shift the assertion by one clock cycle (##1) in order to avoid
  // erroneous SVA triggers right after reset deassertion in cases where
  // the precondition is true throughout the reset.
  // this can happen since the disable_iff evaluates using unsampled values,
  // meaning that the assertion may already read rst_ni == 1 on an active
  // clock edge while the flops in the design have not yet changed state.
  `ASSERT(NextStateCheck_A, ##1 lfsr_en_i && !seed_en_i |=> lfsr_q ==
      compute_next_state(coeffs, $past(entropy_i), $past(lfsr_q)))

  // Only check this if enabled.
  if (StatePermEn) begin : gen_perm_check
    // Check that the supplied permutation is valid.
    logic [LfsrDw-1:0] lfsr_perm_test;
    initial begin : p_perm_check
      lfsr_perm_test = '0;
      for (int k = 0; k < LfsrDw; k++) begin
        lfsr_perm_test[StatePerm[k]] = 1'b1;
      end
      // All bit positions must be marked with 1.
      `ASSERT_I(PermutationCheck_A, &lfsr_perm_test)
    end
  end

`endif

  `ASSERT_INIT(InputWidth_A, LfsrDw >= EntropyDw)
  `ASSERT_INIT(OutputWidth_A, LfsrDw >= StateOutDw)

  // MSB must be one in any case
  `ASSERT(CoeffCheck_A, coeffs[LfsrDw-1])

  // output check
  `ASSERT_KNOWN(OutputKnown_A, state_o)
  if (!StatePermEn && !NonLinearOut) begin : gen_output_sva
    `ASSERT(OutputCheck_A, state_o == StateOutDw'(lfsr_q))
  end
  // if no external input changes the lfsr state, a lockup must not occur (by design)
  //`ASSERT(NoLockups_A, (!entropy_i) && (!seed_en_i) |=> !lockup, clk_i, !rst_ni)
  `ASSERT(NoLockups_A, lfsr_en_i && !entropy_i && !seed_en_i |=> !lockup)

  // this can be disabled if unused in order to not distort coverage
  if (ExtSeedSVA) begin : gen_ext_seed_sva
    // check that external seed is correctly loaded into the state
    // rst_ni is used directly as part of the pre-condition since the usage of rst_ni
    // in disable_iff is unsampled.  See #1985 for more details
    `ASSERT(ExtDefaultSeedInputCheck_A, (seed_en_i && rst_ni) |=> lfsr_q == $past(seed_i))
  end

  // if the external seed mechanism is not used,
  // there is theoretically no way we end up in a lockup condition
  // in order to not distort coverage, this SVA can be disabled in such cases
  if (LockupSVA) begin : gen_lockup_mechanism_sva
    // check that a stuck LFSR is correctly reseeded
    `ASSERT(LfsrLockupCheck_A, lfsr_en_i && lockup && !seed_en_i |=> !lockup)
  end

  // If non-linear output requested, the LFSR width must be a power of 2 and greater than 16.
  if(NonLinearOut) begin : gen_nonlinear_align_check_sva
    `ASSERT_INIT(SboxByteAlign_A, 2**$clog2(LfsrDw) == LfsrDw && LfsrDw >= 16)
  end

  if (MaxLenSVA) begin : gen_max_len_sva
`ifndef SYNTHESIS
    // the code below is a workaround to enable long sequences to be checked.
    // some simulators do not support SVA sequences longer than 2**32-1.
    logic [LfsrDw-1:0] cnt_d, cnt_q;
    logic perturbed_d, perturbed_q;
    logic [LfsrDw-1:0] cmp_val;

    assign cmp_val = {{(LfsrDw-1){1'b1}}, 1'b0}; // 2**LfsrDw-2
    assign cnt_d = (lfsr_en_i && lockup)             ? '0           :
                   (lfsr_en_i && (cnt_q == cmp_val)) ? '0           :
                   (lfsr_en_i)                       ? cnt_q + 1'b1 :
                                                       cnt_q;

    assign perturbed_d = perturbed_q | (|entropy_i) | seed_en_i;

    always_ff @(posedge clk_i or negedge rst_ni) begin : p_max_len
      if (!rst_ni) begin
        cnt_q       <= '0;
        perturbed_q <= 1'b0;
      end else begin
        cnt_q       <= cnt_d;
        perturbed_q <= perturbed_d;
      end
    end

    `ASSERT(MaximalLengthCheck0_A, cnt_q == 0 |-> lfsr_q == DefaultSeedLocal,
        clk_i, !rst_ni || perturbed_q)
    `ASSERT(MaximalLengthCheck1_A, cnt_q != 0 |-> lfsr_q != DefaultSeedLocal,
        clk_i, !rst_ni || perturbed_q)
`endif
  end

endmodule
