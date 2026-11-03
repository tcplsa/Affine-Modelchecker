/- Four 16-bit local carry contracts compose into one 64-bit addition. -/
theorem compose_four_chunks
    (a0 a1 a2 a3 b0 b1 b2 b3 s0 s1 s2 s3 c1 c2 c3 c4 : Nat)
    (h0 : a0 + b0 = s0 + 65536 * c1)
    (h1 : a1 + b1 + c1 = s1 + 65536 * c2)
    (h2 : a2 + b2 + c2 = s2 + 65536 * c3)
    (h3 : a3 + b3 + c3 = s3 + 65536 * c4) :
    (a0 + 65536 * a1 + 4294967296 * a2 + 281474976710656 * a3) +
    (b0 + 65536 * b1 + 4294967296 * b2 + 281474976710656 * b3) =
    s0 + 65536 * s1 + 4294967296 * s2 + 281474976710656 * s3 +
      18446744073709551616 * c4 := by
  omega

