"""
Static question bank for Rehearsal.
Organized by domain -> difficulty tier -> list of question strings.
"""

QUESTION_BANK: dict = {
    "backend": {
        "easy": [
            "What is the difference between SQL and NoSQL databases? Give an example of when you'd choose each.",
            "Explain what REST means and describe the key constraints of a RESTful API.",
            "What is the purpose of an index in a database, and what trade-offs does it introduce?",
            "Describe the request-response lifecycle of an HTTP request hitting a backend server.",
            "What is the difference between authentication and authorization? How would you implement each?",
        ],
        "medium": [
            "Walk us through how you would design a rate-limiting system for a public API. What data structures would you use?",
            "Explain the CAP theorem and describe a real system that consciously trades off one of the three properties.",
            "How would you approach debugging a backend service that has a sudden spike in p99 latency?",
            "Design a job queue system that guarantees at-least-once delivery. What are the failure modes?",
            "Explain database connection pooling — why it exists, how it works, and what happens when the pool is exhausted.",
            "What is an N+1 query problem and how do you detect and fix it in an ORM-heavy codebase?",
        ],
        "hard": [
            "You need to build a distributed lock across 5 nodes where any node can fail at any time. Walk us through your approach.",
            "Design a multi-tenant SaaS backend where each tenant can have custom business logic without you deploying per-tenant code.",
            "Your team's PostgreSQL primary is falling behind replicas by 30 seconds under peak load. Diagnose and resolve.",
            "Explain how you'd implement exactly-once semantics in a Kafka consumer pipeline that writes to a database.",
            "Design the data model and API for a collaborative document editing system that supports offline-first changes.",
        ],
    },
    "frontend": {
        "easy": [
            "What is the difference between `null` and `undefined` in JavaScript, and when does each appear?",
            "Explain the browser's critical rendering path — what steps does the browser take from HTML to pixels?",
            "What is event delegation and why is it useful in large list-based UIs?",
            "Describe the difference between `==` and `===` in JavaScript with concrete examples.",
            "What is the purpose of the `key` prop in React lists and what happens if you omit it?",
        ],
        "medium": [
            "Explain React's reconciliation algorithm. How does it decide what to re-render?",
            "Walk us through how you'd optimise a React application that has noticeable jank on a mid-range mobile device.",
            "What is the difference between debouncing and throttling? Build a use-case for each from scratch.",
            "Explain the JavaScript event loop, microtask queue, and macrotask queue with a code example.",
            "How would you architect a large React application's state management — what trade-offs exist between Context, Redux, and Zustand?",
            "What are CSS custom properties (variables) and how do they differ from pre-processor variables like SASS?",
        ],
        "hard": [
            "Design a virtual scrolling component from scratch for a list of 1 million items. Walk through the maths and the DOM strategy.",
            "How would you implement a rich-text editor (bold, italic, links, lists) without using any third-party library?",
            "Explain how module federation works in Webpack 5 and how you'd use it to build a microfrontend architecture.",
            "You've inherited a React codebase with dozens of components re-rendering on every keystroke. Describe your systematic debugging and remediation strategy.",
            "Design a drag-and-drop kanban board that preserves order correctly under concurrent user updates via WebSockets.",
        ],
    },
    "system_design": {
        "easy": [
            "What is horizontal vs vertical scaling? Give an example of a system that benefits more from one than the other.",
            "Explain what a CDN is and describe how it improves both latency and origin load.",
            "What is a load balancer and what are the common strategies for distributing requests?",
            "Describe the difference between synchronous and asynchronous communication between services.",
            "What is caching and what are the main invalidation strategies?",
        ],
        "medium": [
            "Design a URL shortener service. Cover storage, redirect latency, and how you'd handle 1 billion URLs.",
            "How would you design a notification system that delivers to email, SMS, and push simultaneously? Handle failures gracefully.",
            "Explain consistent hashing — how it works and why it's used in distributed caches and load balancers.",
            "Design a leaderboard system for a mobile game with 10 million daily active users. Prioritise read performance.",
            "Walk us through designing a search-as-you-type autocomplete API that serves results in under 100 ms globally.",
        ],
        "hard": [
            "Design a globally distributed key-value store with tunable consistency. How do you handle cross-region replication lag?",
            "Design YouTube's video ingestion and transcoding pipeline. Account for encoding parallelism and storage costs.",
            "How would you design a fraud detection system that must make a pass/fail decision in under 200 ms per transaction?",
            "Design a real-time collaborative whiteboard for 10,000 concurrent users on a single canvas. Handle conflict resolution.",
            "Describe how you'd architect a multi-region active-active database setup with zero-RPO failover.",
        ],
    },
}


def get_questions(domain: str, difficulty: str) -> list[str]:
    """Return the question list for a given domain and difficulty."""
    return QUESTION_BANK.get(domain, {}).get(difficulty, [])


def get_next_question(domain: str, difficulty: str, asked: set[str]) -> str | None:
    """
    Return the next unasked question for the domain/difficulty pair.
    Returns None if all questions at this tier have been exhausted.
    """
    questions = get_questions(domain, difficulty)
    for q in questions:
        if q not in asked:
            return q
    return None
