Cauchy-based Reed-Solomon Erasure Codes
========================================

This is the reference implementation of Cauchy-based Reed-Solomon erasure
resilient codes, originally developed in 1993-1994 by Michael Luby at the
International Computer Science Institute (ICSI) for the PET project.

Theory
------

The algorithm is described in ICSI Technical Report TR-95-048:

  "An XOR-Based Erasure-Resilient Coding Scheme"
  Johannes Bloemer, Malik Kalfane, Marek Karpinski,
  Richard Karp, Michael Luby, David Zuckerman

Original paper: http://www1.icsi.berkeley.edu/~luby/

Overview
--------

This implementation provides Forward Error Correction (FEC) using
Cauchy matrices over GF(2^Lfield).  Unlike classic Reed-Solomon codes
that require general finite-field multiplication, the Cauchy
construction allows all encoding and decoding operations to be
performed with XOR only, making it significantly faster in software.

Workflow
--------

  1. Init_field  - Build lookup tables for GF(2^Lfield) arithmetic
  2. Get_msg     - Generate (or load) the original message
  3. Encode      - Produce Mpackets message packets + Rpackets redundant packets
  4. Lose_Packets - Simulate packet loss on the encoded stream
  5. Decode      - Recover the original message from surviving packets
  6. Compare_msg - Verify the decoded message matches the original

Source Files
------------

  driver.c        - Main program: runs the full encode/decode cycle
  parameters.h    - All configurable parameters (field size, packet counts)
  init_field.c/h  - GF(2^Lfield) table initialization
  get_msg.c/h     - Message generation
  encode.c/h      - Cauchy encoding
  lose_packets.c/h- Simulated packet loss
  decode.c/h      - Cauchy decoding
  compare_msg.c/h - Verification

Key Parameters (parameters.h)
------------------------------

  Lfield    = 10    Log2 of the Galois field size (max 10 for this code)
  Nsegs     = 25    Number of segments per packet
  Mpackets  = 200   Number of message packets
  Rpackets  = 200   Number of redundant packets

  Constraint: max(Mpackets, Rpackets) <= 2^(Lfield - 1)

  With the defaults:
    Packet size = 4 * Nsegs * Lfield = 1000 bytes
    Total data  = Mpackets * Packet size = 200,000 bytes
    Encoding    = (Mpackets + Rpackets) * Packet size = 400,000 bytes
    Redundancy  = 2.0x  (can tolerate loss of up to Rpackets = 200 packets)

Building
--------

    make

This produces the `driver` executable.

Running
-------

    make test

-or-

    ./driver

The driver runs one iteration (Niter=1) of encoding and decoding,
measures throughput, and prints whether decoding was successful.

Sample output:

    --------------------------------------
    Iteration 0.

    Done getting message of 200000 bytes
    ------------------------------------------------
     encode: number of seconds is X.XXXXXX
    ------------------------------------------------

    Done encoding 400 packets
    Received 200 packets with seed XXXXX
    Nfirstrec= 0, Nextra= 200
    ------------------------------------------------
     decode: number of seconds is X.XXXXXX
    ------------------------------------------------

    Done with decoding
    Done with comparison
    --------- Cauchy Code ---------------
    Number of Mbytes processed is X.XXXXXX
    Time in seconds is X.XXXXXX
    MBytes per second is X.XXXXXX
    Overhead is 200
    Encoding redundancy is 2.000000
    Fraction of packets received is 0.500000

Cleanup
-------

    make clean

License
-------

Non-commercial evaluation license from ICSI.  Commercial use requires
written permission from the International Computer Science Institute,
1947 Center Street, Suite 600, Berkeley, CA 94704, USA.
