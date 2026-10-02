.. req:: REQ_SCORE_TCQ_001
   :id: REQ_SCORE_TCQ_001
   :status: implemented
   :safety: ASIL-B
   :verification_method: UT
   :tags: BoundedCapacity, MemorySafety

   The `TimedCommandQueue` shall have a compile-time configurable, fixed maximum capacity to prevent unbounded resource consumption.

.. req:: REQ_SCORE_TCQ_002
   :id: REQ_SCORE_TCQ_002
   :status: implemented
   :safety: ASIL-B
   :verification_method: UT
   :tags: OverflowPolicy, DataIntegrity

   When the `TimedCommandQueue` is full and a new command is to be registered, the oldest existing command in the queue shall be removed to accommodate the new command.

.. req:: REQ_SCORE_TCQ_003
   :id: REQ_SCORE_TCQ_003
   :status: implemented
   :safety: ASIL-B
   :verification_method: UT
   :tags: ErrorHandling, Notification

   The `TimedCommandQueue` shall provide a mechanism, such as a callback, to notify system components when a command is dropped due to queue overflow.

.. req:: REQ_SCORE_TCQ_004
   :id: REQ_SCORE_TCQ_004
   :status: implemented
   :safety: ASIL-B
   :verification_method: UT, MR
   :tags: MemorySafety, EmbeddedSystems

   The `TimedCommandQueue` shall not perform any dynamic memory allocations during its operational lifetime after construction.

.. req:: REQ_SCORE_TCQ_005
   :id: REQ_SCORE_TCQ_005
   :status: implemented
   :safety: ASIL-B
   :verification_method: UT, HI
   :tags: Concurrency, ThreadSafety

   All public member functions of the `TimedCommandQueue` shall be thread-safe for concurrent access by multiple threads.

.. req:: REQ_SCORE_TCQ_006
   :id: REQ_SCORE_TCQ_006
   :status: implemented
   :safety: ASIL-B
   :verification_method: UT, HI, MR
   :tags: ExceptionSafety, Robustness

   All member functions of the `TimedCommandQueue` shall be declared `noexcept` to ensure predictable behavior and prevent exceptions from propagating.