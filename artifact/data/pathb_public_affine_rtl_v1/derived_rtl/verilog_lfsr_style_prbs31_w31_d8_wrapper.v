// Sequential equivalence wrapper for the two implementation styles exported
// by alexforencich/verilog-lfsr.  The upstream lfsr.v is not modified.
module verilog_lfsr_style_formal #(
    parameter LFSR_WIDTH = 16,
    parameter LFSR_POLY = 16'h1021,
    parameter LFSR_CONFIG = "FIBONACCI",
    parameter REVERSE = 0,
    parameter DATA_WIDTH = 8
) (
    input wire clk,
    input wire rst,
    input wire enable,
    input wire [DATA_WIDTH-1:0] data_in,
    output wire bad
);
    reg [LFSR_WIDTH-1:0] loop_state;
    reg [LFSR_WIDTH-1:0] reduction_state;
    wire [LFSR_WIDTH-1:0] loop_next;
    wire [LFSR_WIDTH-1:0] reduction_next;
    wire [DATA_WIDTH-1:0] loop_data;
    wire [DATA_WIDTH-1:0] reduction_data;

    initial begin
        loop_state = {LFSR_WIDTH{1'b1}};
        reduction_state = {LFSR_WIDTH{1'b1}};
    end

    lfsr #(
        .LFSR_WIDTH(LFSR_WIDTH),
        .LFSR_POLY(LFSR_POLY),
        .LFSR_CONFIG(LFSR_CONFIG),
        .LFSR_FEED_FORWARD(0),
        .REVERSE(REVERSE),
        .DATA_WIDTH(DATA_WIDTH),
        .STYLE("LOOP")
    ) loop_impl (
        .data_in(data_in),
        .state_in(loop_state),
        .data_out(loop_data),
        .state_out(loop_next)
    );

    lfsr #(
        .LFSR_WIDTH(LFSR_WIDTH),
        .LFSR_POLY(LFSR_POLY),
        .LFSR_CONFIG(LFSR_CONFIG),
        .LFSR_FEED_FORWARD(0),
        .REVERSE(REVERSE),
        .DATA_WIDTH(DATA_WIDTH),
        .STYLE("REDUCTION")
    ) reduction_impl (
        .data_in(data_in),
        .state_in(reduction_state),
        .data_out(reduction_data),
        .state_out(reduction_next)
    );

    assign bad = (loop_state != reduction_state)
        || (loop_data != reduction_data)
        || (loop_next != reduction_next);

    always @(posedge clk) begin
        if (rst) begin
            loop_state <= {LFSR_WIDTH{1'b1}};
            reduction_state <= {LFSR_WIDTH{1'b1}};
        end else if (enable) begin
            loop_state <= loop_next;
            reduction_state <= reduction_next;
        end
    end
endmodule
