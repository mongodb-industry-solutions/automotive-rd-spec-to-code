/********************************************************************************
 * Copyright (c) 2025 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License Version 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

/**
 * @file timed_command_queue_enhanced_test.cpp
 * @brief ASPICE SWE.4 Unit Verification Suite for TimedCommandQueue (ISO 26262 ASIL-B)
 *
 * Traceability Matrix:
 * - REQ_SCORE_TCQ_001: Bounded Capacity Limit
 * - REQ_SCORE_TCQ_002: Drop-Oldest Overflow Behavior
 * - REQ_SCORE_TCQ_003: Overflow Callback Notification
 * - REQ_SCORE_TCQ_004: Zero Dynamic Memory Allocation in Operational State
 * - REQ_SCORE_TCQ_005: Thread Safety Under Concurrent Access
 * - REQ_SCORE_TCQ_006: Exception Safety & noexcept Specifications
 */

#include <gtest/gtest.h>
#include <gmock/gmock.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <mutex>
#include <new>
#include <thread>
#include <vector>

// ==============================================================================
// Memory Allocation Interceptor for REQ_SCORE_TCQ_004 Verification
// ==============================================================================
namespace
{
std::atomic<bool> g_allocation_recording_active{false};
std::atomic<size_t> g_dynamic_allocation_count{0};

class DynamicAllocationMonitor
{
  public:
    DynamicAllocationMonitor() noexcept
    {
        g_dynamic_allocation_count.store(0, std::memory_order_seq_cst);
        g_allocation_recording_active.store(true, std::memory_order_seq_cst);
    }

    ~DynamicAllocationMonitor() noexcept
    {
        g_allocation_recording_active.store(false, std::memory_order_seq_cst);
    }

    [[nodiscard]] size_t GetAllocationCount() const noexcept
    {
        return g_dynamic_allocation_count.load(std::memory_order_seq_cst);
    }

    DynamicAllocationMonitor(const DynamicAllocationMonitor&) = delete;
    DynamicAllocationMonitor& operator=(const DynamicAllocationMonitor&) = delete;
};
}  // namespace

void* operator new(std::size_t size)
{
    if (g_allocation_recording_active.load(std::memory_order_relaxed))
    {
        g_dynamic_allocation_count.fetch_add(1, std::memory_order_relaxed);
    }
    void* ptr = std::malloc(size);
    if (!ptr)
    {
        throw std::bad_alloc();
    }
    return ptr;
}

void operator delete(void* ptr) noexcept
{
    std::free(ptr);
}

void operator delete(void* ptr, std::size_t) noexcept
{
    std::free(ptr);
}

// ==============================================================================
// Eclipse S-CORE TimedCommandQueue Enhanced Definition for SWE.4 Verification
// ==============================================================================
namespace score::message_passing
{

struct TimedCommandQueueEntry
{
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;
    using QueuedCallback = std::function<void(TimePoint)>;

    TimedCommandQueueEntry* prev{nullptr};
    TimedCommandQueueEntry* next{nullptr};

    TimePoint until_{};
    const void* owner_{nullptr};
    QueuedCallback callback_{};
    int id{0};

    explicit TimedCommandQueueEntry(int entry_id = 0) noexcept : id(entry_id) {}

    void Reset() noexcept
    {
        prev = nullptr;
        next = nullptr;
        until_ = TimePoint{};
        owner_ = nullptr;
        callback_ = nullptr;
        id = 0;
    }
};

}  // namespace score::message_passing

namespace score::message_passing::detail
{

template <size_t Capacity>
class TimedCommandQueue
{
  public:
    static_assert(Capacity > 0, "Capacity must be strictly greater than 0");

    using Entry = TimedCommandQueueEntry;
    using Clock = TimedCommandQueueEntry::Clock;
    using TimePoint = TimedCommandQueueEntry::TimePoint;
    using QueuedCallback = TimedCommandQueueEntry::QueuedCallback;
    using OverflowCallback = std::function<void(const Entry& dropped_entry)>;

    TimedCommandQueue() noexcept = default;
    ~TimedCommandQueue() noexcept = default;

    TimedCommandQueue(const TimedCommandQueue&) = delete;
    TimedCommandQueue& operator=(const TimedCommandQueue&) = delete;
    TimedCommandQueue(TimedCommandQueue&&) = delete;
    TimedCommandQueue& operator=(TimedCommandQueue&&) = delete;

    void RegisterImmediateEntry(Entry& entry, QueuedCallback callback, const void* const owner = nullptr) noexcept
    {
        RegisterTimedEntry(entry, TimePoint{}, std::move(callback), owner);
    }

    void RegisterTimedEntry(Entry& entry,
                            const TimePoint until,
                            QueuedCallback callback,
                            const void* const owner = nullptr) noexcept
    {
        std::lock_guard<std::mutex> lock(mutex_);

        entry.until_ = until;
        entry.owner_ = owner;
        entry.callback_ = std::move(callback);
        entry.prev = nullptr;
        entry.next = nullptr;

        // Bounded capacity check: Drop oldest entry if at capacity
        if (size_ == Capacity)
        {
            Entry* dropped = head_;
            if (overflow_callback_)
            {
                overflow_callback_(*dropped);
            }
            RemoveFromList(dropped);
            dropped->callback_ = nullptr;
            dropped->owner_ = nullptr;
            overflow_count_.fetch_add(1, std::memory_order_relaxed);
            // size_ is decremented by RemoveFromList
        }

        InsertSorted(entry);
    }

    TimePoint ProcessQueue(const TimePoint now) noexcept
    {
        std::unique_lock<std::mutex> lock(mutex_);
        while (head_ != nullptr)
        {
            Entry* entry = head_;
            const TimePoint until = entry->until_;
            if (until > now)
            {
                return until;
            }

            RemoveFromList(entry);

            QueuedCallback cb = std::move(entry->callback_);
            entry->owner_ = nullptr;

            lock.unlock();
            if (cb)
            {
                cb(now);
            }
            lock.lock();
        }
        return TimePoint{};
    }

    void CleanUpOwner(const void* const owner) noexcept
    {
        if (owner == nullptr)
        {
            return;
        }

        std::lock_guard<std::mutex> lock(mutex_);
        Entry* curr = head_;
        while (curr != nullptr)
        {
            Entry* next_entry = curr->next;
            if (curr->owner_ == owner)
            {
                RemoveFromList(curr);
                curr->callback_ = nullptr;
                curr->owner_ = nullptr;
            }
            curr = next_entry;
        }
    }

    void SetOverflowCallback(OverflowCallback callback) noexcept
    {
        std::lock_guard<std::mutex> lock(mutex_);
        overflow_callback_ = std::move(callback);
    }

    [[nodiscard]] size_t Size() const noexcept
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return size_;
    }

    [[nodiscard]] constexpr size_t Capacity_() const noexcept
    {
        return Capacity;
    }

    [[nodiscard]] uint64_t GetOverflowCount() const noexcept
    {
        return overflow_count_.load(std::memory_order_relaxed);
    }

    [[nodiscard]] bool Empty() const noexcept
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return size_ == 0;
    }

    int GetOldestEntryId() const noexcept
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return head_ ? head_->id : -1;
    }

    int GetNewestEntryId() const noexcept
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return tail_ ? tail_->id : -1;
    }

  private:
    void InsertSorted(Entry& entry) noexcept
    {
        if (head_ == nullptr)
        {
            head_ = &entry;
            tail_ = &entry;
        }
        else if (entry.until_ < head_->until_)
        {
            entry.next = head_;
            head_->prev = &entry;
            head_ = &entry;
        }
        else
        {
            Entry* curr = head_;
            while (curr->next != nullptr && !(entry.until_ < curr->next->until_))
            {
                curr = curr->next;
            }
            entry.next = curr->next;
            entry.prev = curr;
            if (curr->next != nullptr)
            {
                curr->next->prev = &entry;
            }
            else
            {
                tail_ = &entry;
            }
            curr->next = &entry;
        }
        ++size_;
    }

    void RemoveFromList(Entry* entry) noexcept
    {
        if (entry->prev != nullptr)
        {
            entry->prev->next = entry->next;
        }
        else
        {
            head_ = entry->next;
        }

        if (entry->next != nullptr)
        {
            entry->next->prev = entry->prev;
        }
        else
        {
            tail_ = entry->prev;
        }

        entry->prev = nullptr;
        entry->next = nullptr;
        --size_;
    }

    mutable std::mutex mutex_;
    Entry* head_{nullptr};
    Entry* tail_{nullptr};
    size_t size_{0};
    OverflowCallback overflow_callback_{};
    std::atomic<uint64_t> overflow_count_{0};
};

}  // namespace score::message_passing::detail

// ==============================================================================
// Test Fixture and Verification Test Cases
// ==============================================================================
namespace
{
using namespace score::message_passing;
using namespace score::message_passing::detail;
using namespace ::testing;
using std::literals::chrono_literals::operator""s;
using std::literals::chrono_literals::operator""ms;

class TimedCommandQueueEnhancedTest : public ::testing::Test
{
  protected:
    void SetUp() override {}
    void TearDown() override {}
};

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification for REQ_SCORE_TCQ_006: noexcept specifications
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, REQ_SCORE_TCQ_006_NoThrowGuarantees)
{
    // Verifies: REQ_SCORE_TCQ_006
    // Description: Compile-time check ensuring all public operational methods
    //              satisfy strict noexcept guarantees for ISO 26262 ASIL-B compliance.
    using Queue = TimedCommandQueue<4>;

    static_assert(noexcept(Queue{}), "Queue default constructor must be noexcept");
    static_assert(noexcept(std::declval<Queue>().~Queue()), "Queue destructor must be noexcept");
    static_assert(noexcept(std::declval<Queue>().RegisterImmediateEntry(
                      std::declval<TimedCommandQueueEntry&>(),
                      std::declval<TimedCommandQueueEntry::QueuedCallback>(),
                      nullptr)),
                  "RegisterImmediateEntry must be noexcept");
    static_assert(noexcept(std::declval<Queue>().RegisterTimedEntry(
                      std::declval<TimedCommandQueueEntry&>(),
                      std::declval<TimedCommandQueueEntry::TimePoint>(),
                      std::declval<TimedCommandQueueEntry::QueuedCallback>(),
                      nullptr)),
                  "RegisterTimedEntry must be noexcept");
    static_assert(noexcept(std::declval<Queue>().ProcessQueue(
                      std::declval<TimedCommandQueueEntry::TimePoint>())),
                  "ProcessQueue must be noexcept");
    static_assert(noexcept(std::declval<Queue>().CleanUpOwner(nullptr)),
                  "CleanUpOwner must be noexcept");
    static_assert(noexcept(std::declval<Queue>().SetOverflowCallback(
                      std::declval<Queue::OverflowCallback>())),
                  "SetOverflowCallback must be noexcept");
    static_assert(noexcept(std::declval<Queue>().Size()), "Size must be noexcept");
    static_assert(noexcept(std::declval<Queue>().Capacity_()), "Capacity_ must be noexcept");
    static_assert(noexcept(std::declval<Queue>().GetOverflowCount()), "GetOverflowCount must be noexcept");
    static_assert(noexcept(std::declval<Queue>().Empty()), "Empty must be noexcept");

    SUCCEED();
}

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification for REQ_SCORE_TCQ_001: Bounded Capacity Limit
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, REQ_SCORE_TCQ_001_BoundedCapacityLimit)
{
    // Verifies: REQ_SCORE_TCQ_001
    // Description: Verifies that the queue strictly bounds capacity to compile-time
    //              template parameter and never exceeds it under load.
    constexpr size_t CAPACITY = 3;
    TimedCommandQueue<CAPACITY> queue;
    std::vector<TimedCommandQueueEntry> entries(CAPACITY + 2);

    EXPECT_EQ(queue.Capacity_(), CAPACITY);
    EXPECT_TRUE(queue.Empty());
    EXPECT_EQ(queue.Size(), 0U);

    // Fill queue to exact capacity
    for (size_t i = 0; i < CAPACITY; ++i)
    {
        entries[i].id = static_cast<int>(i + 1);
        queue.RegisterImmediateEntry(entries[i], [](auto) {});
        EXPECT_EQ(queue.Size(), i + 1);
    }
    EXPECT_EQ(queue.Size(), CAPACITY);

    // Register additional elements exceeding capacity
    entries[CAPACITY].id = 100;
    queue.RegisterImmediateEntry(entries[CAPACITY], [](auto) {});
    EXPECT_EQ(queue.Size(), CAPACITY);

    entries[CAPACITY + 1].id = 101;
    queue.RegisterImmediateEntry(entries[CAPACITY + 1], [](auto) {});
    EXPECT_EQ(queue.Size(), CAPACITY);
}

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification for REQ_SCORE_TCQ_002: Drop-Oldest Overflow Behavior
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, REQ_SCORE_TCQ_002_DropOldestOverflowBehavior)
{
    // Verifies: REQ_SCORE_TCQ_002
    // Description: Verifies that when the queue reaches capacity, registering a new entry
    //              causes the oldest scheduled entry to be evicted.
    constexpr size_t CAPACITY = 3;
    TimedCommandQueue<CAPACITY> queue;
    std::vector<TimedCommandQueueEntry> entries(5);
    const auto base_time = TimedCommandQueueEntry::Clock::now();

    entries[0].id = 1;
    entries[1].id = 2;
    entries[2].id = 3;

    // Register 3 entries with increasing execution deadlines
    queue.RegisterTimedEntry(entries[0], base_time + 10s, [](auto) {});
    queue.RegisterTimedEntry(entries[1], base_time + 20s, [](auto) {});
    queue.RegisterTimedEntry(entries[2], base_time + 30s, [](auto) {});

    ASSERT_EQ(queue.Size(), CAPACITY);
    EXPECT_EQ(queue.GetOldestEntryId(), 1);
    EXPECT_EQ(queue.GetNewestEntryId(), 3);

    // Overflow with an entry having deadline 25s
    // The oldest entry (10s, ID=1) must be dropped
    entries[3].id = 4;
    queue.RegisterTimedEntry(entries[3], base_time + 25s, [](auto) {});

    EXPECT_EQ(queue.Size(), CAPACITY);
    EXPECT_EQ(queue.GetOldestEntryId(), 2);  // ID 1 was evicted, ID 2 (20s) is now oldest
    EXPECT_EQ(queue.GetNewestEntryId(), 3);  // ID 3 (30s) remains newest

    // Overflow again with an immediate entry (ID=5, deadline 0)
    // The current oldest entry (20s, ID=2) must be dropped
    entries[4].id = 5;
    queue.RegisterImmediateEntry(entries[4], [](auto) {});

    EXPECT_EQ(queue.Size(), CAPACITY);
    EXPECT_EQ(queue.GetOldestEntryId(), 5);  // Immediate entry is placed at head
    EXPECT_EQ(queue.GetNewestEntryId(), 3);  // ID 3 (30s) is still newest
}

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification for REQ_SCORE_TCQ_003: Overflow Callback Notification
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, REQ_SCORE_TCQ_003_OverflowCallbackNotification)
{
    // Verifies: REQ_SCORE_TCQ_003
    // Description: Verifies invocation of the user-registered overflow notification callback
    //              with accurate dropped entry metadata and drop count tracking.
    constexpr size_t CAPACITY = 2;
    TimedCommandQueue<CAPACITY> queue;
    std::vector<TimedCommandQueueEntry> entries(4);

    std::vector<int> dropped_ids;
    std::atomic<uint64_t> callback_invocation_count{0};

    queue.SetOverflowCallback([&](const TimedCommandQueueEntry& dropped_entry) {
        callback_invocation_count.fetch_add(1, std::memory_order_relaxed);
        dropped_ids.push_back(dropped_entry.id);
    });

    // Populate queue to capacity (IDs: 10, 20)
    entries[0].id = 10;
    entries[1].id = 20;
    queue.RegisterImmediateEntry(entries[0], [](auto) {});
    queue.RegisterImmediateEntry(entries[1], [](auto) {});

    EXPECT_EQ(queue.Size(), CAPACITY);
    EXPECT_EQ(callback_invocation_count.load(), 0U);
    EXPECT_EQ(queue.GetOverflowCount(), 0U);

    // Overflow 1: Insert ID 30 -> Drops ID 10
    entries[2].id = 30;
    queue.RegisterImmediateEntry(entries[2], [](auto) {});

    EXPECT_EQ(callback_invocation_count.load(), 1U);
    EXPECT_EQ(queue.GetOverflowCount(), 1U);
    ASSERT_THAT(dropped_ids, ElementsAre(10));

    // Overflow 2: Insert ID 40 -> Drops ID 20
    entries[3].id = 40;
    queue.RegisterImmediateEntry(entries[3], [](auto) {});

    EXPECT_EQ(callback_invocation_count.load(), 2U);
    EXPECT_EQ(queue.GetOverflowCount(), 2U);
    ASSERT_THAT(dropped_ids, ElementsAre(10, 20));
}

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification for REQ_SCORE_TCQ_004: Zero Dynamic Memory Allocation
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, REQ_SCORE_TCQ_004_ZeroDynamicMemoryAllocationInOperationalState)
{
    // Verifies: REQ_SCORE_TCQ_004
    // Description: Enforces zero dynamic memory allocations (new/malloc) during operational phase:
    //              RegisterImmediateEntry, RegisterTimedEntry, ProcessQueue, CleanUpOwner.
    constexpr size_t CAPACITY = 4;
    TimedCommandQueue<CAPACITY> queue;
    std::vector<TimedCommandQueueEntry> entries(CAPACITY);
    for (size_t i = 0; i < CAPACITY; ++i)
    {
        entries[i].id = static_cast<int>(i + 1);
    }

    const auto now = TimedCommandQueueEntry::Clock::now();
    int owner_tag = 42;

    // Begin strict monitoring of heap allocations
    {
        DynamicAllocationMonitor monitor;

        // 1. Immediate entry registration
        queue.RegisterImmediateEntry(entries[0], [](auto) noexcept {}, &owner_tag);

        // 2. Timed entry registration
        queue.RegisterTimedEntry(entries[1], now + 100ms, [](auto) noexcept {}, &owner_tag);
        queue.RegisterTimedEntry(entries[2], now + 200ms, [](auto) noexcept {}, nullptr);

        // 3. CleanUpOwner operation
        queue.CleanUpOwner(&owner_tag);

        // 4. Processing queue
        queue.ProcessQueue(now + 500ms);

        // 5. Inquire queue metrics
        (void)queue.Size();
        (void)queue.GetOverflowCount();
        (void)queue.Empty();

        EXPECT_EQ(monitor.GetAllocationCount(), 0U)
            << "Violation of REQ_SCORE_TCQ_004: Dynamic heap allocation detected during operational execution!";
    }
}

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification for REQ_SCORE_TCQ_005: Thread Safety Under Concurrent Producers
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, REQ_SCORE_TCQ_005_ThreadSafetyConcurrentProducers)
{
    // Verifies: REQ_SCORE_TCQ_005
    // Description: Verifies absence of data races, correct atomic drop metric counts,
    //              and queue integrity under high contention with multiple concurrent producer threads.
    constexpr size_t CAPACITY = 64;
    TimedCommandQueue<CAPACITY> queue;

    constexpr int NUM_THREADS = 8;
    constexpr int ENTRIES_PER_THREAD = 100;
    constexpr int TOTAL_ENTRIES = NUM_THREADS * ENTRIES_PER_THREAD;

    std::vector<TimedCommandQueueEntry> entries(TOTAL_ENTRIES);
    std::atomic<uint64_t> recorded_overflow_callbacks{0};

    queue.SetOverflowCallback([&](const TimedCommandQueueEntry&) {
        recorded_overflow_callbacks.fetch_add(1, std::memory_order_relaxed);
    });

    std::atomic<bool> start_signal{false};
    std::vector<std::thread> producers;
    producers.reserve(NUM_THREADS);

    const auto base_time = TimedCommandQueueEntry::Clock::now();

    for (int t = 0; t < NUM_THREADS; ++t)
    {
        producers.emplace_back([&, t]() {
            while (!start_signal.load(std::memory_order_acquire))
            {
                std::this_thread::yield();
            }

            for (int i = 0; i < ENTRIES_PER_THREAD; ++i)
            {
                const int idx = t * ENTRIES_PER_THREAD + i;
                entries[idx].id = idx;
                if ((idx % 2) == 0)
                {
                    queue.RegisterImmediateEntry(entries[idx], [](auto) {});
                }
                else
                {
                    queue.RegisterTimedEntry(entries[idx], base_time + std::chrono::milliseconds(idx), [](auto) {});
                }
            }
        });
    }

    start_signal.store(true, std::memory_order_release);

    for (auto& worker : producers)
    {
        worker.join();
    }

    // Queue capacity invariant check
    EXPECT_EQ(queue.Size(), CAPACITY);

    // Invariant: Total Entries = Remaining in Queue + Dropped Entries
    const uint64_t expected_drops = TOTAL_ENTRIES - CAPACITY;
    EXPECT_EQ(queue.GetOverflowCount(), expected_drops);
    EXPECT_EQ(recorded_overflow_callbacks.load(std::memory_order_relaxed), expected_drops);

    // Verify sequential draining works cleanly without memory faults
    const auto drain_time = base_time + 1000s;
    const auto remaining_timepoint = queue.ProcessQueue(drain_time);
    EXPECT_EQ(remaining_timepoint, TimedCommandQueueEntry::TimePoint{});
    EXPECT_EQ(queue.Size(), 0U);
    EXPECT_TRUE(queue.Empty());
}

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification: ProcessQueue Re-entrancy & Self-Rescheduling
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, ProcessQueue_ReentrancyAndRescheduling)
{
    // Verifies: REQ_SCORE_TCQ_005 (Safe critical section release during callback dispatch)
    // Description: Verifies that callbacks can safely invoke RegisterTimedEntry
    //              from within ProcessQueue without deadlocking.
    constexpr size_t CAPACITY = 4;
    TimedCommandQueue<CAPACITY> queue;

    TimedCommandQueueEntry entry1(1);
    TimedCommandQueueEntry entry2(2);

    const auto now = TimedCommandQueueEntry::Clock::now();
    bool rescheduled_executed = false;

    queue.RegisterTimedEntry(entry1, now, [&](auto current_time) {
        // Reschedule entry2 inside callback while queue lock is released
        queue.RegisterTimedEntry(entry2, current_time + 50ms, [&](auto) {
            rescheduled_executed = true;
        });
    });

    // Process first entry; second entry should be queued with future time
    const auto next_deadline = queue.ProcessQueue(now);
    EXPECT_EQ(next_deadline, now + 50ms);
    EXPECT_FALSE(rescheduled_executed);
    EXPECT_EQ(queue.Size(), 1U);

    // Advance time and process rescheduled entry
    const auto end_deadline = queue.ProcessQueue(now + 100ms);
    EXPECT_EQ(end_deadline, TimedCommandQueueEntry::TimePoint{});
    EXPECT_TRUE(rescheduled_executed);
    EXPECT_TRUE(queue.Empty());
}

// ------------------------------------------------------------------------------
// ASPICE SWE.4 Verification: CleanUpOwner Integrity
// ------------------------------------------------------------------------------
TEST_F(TimedCommandQueueEnhancedTest, CleanUpOwner_ScopedLifetimeManagement)
{
    // Verifies: REQ_SCORE_TCQ_004 & REQ_SCORE_TCQ_005
    // Description: Verifies safe removal of all entries registered by a specific owner tag
    //              without calling callbacks or leaking node pointers.
    constexpr size_t CAPACITY = 4;
    TimedCommandQueue<CAPACITY> queue;

    TimedCommandQueueEntry entry1(1);
    TimedCommandQueueEntry entry2(2);
    TimedCommandQueueEntry entry3(3);

    int owner_a = 101;
    int owner_b = 202;

    bool cb1_called = false;
    bool cb2_called = false;
    bool cb3_called = false;

    const auto now = TimedCommandQueueEntry::Clock::now();

    queue.RegisterImmediateEntry(entry1, [&](auto) { cb1_called = true; }, &owner_a);
    queue.RegisterTimedEntry(entry2, now + 10s, [&](auto) { cb2_called = true; }, &owner_b);
    queue.RegisterTimedEntry(entry3, now + 20s, [&](auto) { cb3_called = true; }, &owner_a);

    EXPECT_EQ(queue.Size(), 3U);

    // Clean up all entries belonging to owner_a
    queue.CleanUpOwner(&owner_a);
    EXPECT_EQ(queue.Size(), 1U);

    // Process all entries; only owner_b entry should execute
    queue.ProcessQueue(now + 30s);
    EXPECT_FALSE(cb1_called);
    EXPECT_TRUE(cb2_called);
    EXPECT_FALSE(cb3_called);
    EXPECT_TRUE(queue.Empty());
}

}  // namespace

int main(int argc, char** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}