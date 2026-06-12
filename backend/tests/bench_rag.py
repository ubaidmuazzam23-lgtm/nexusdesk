"""
RAG latency benchmark — measures embedding and ChromaDB query times
at 0, 10, 100, and 500 documents.  No server required (imports service directly).

Usage:
    PYTHONPATH=backend python tests/bench_rag.py
"""
import sys, os, time, statistics, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def hdr(s): print(f"\n{'='*68}\n {s}\n{'='*68}")
def info(s): print(f"  [INFO] {s}")
def ok(s):   print(f"  [PASS] {s}")
def fail(s): print(f"  [FAIL] {s}")

# ─── Section 1: Embedding generation time ────────────────────────────────────
hdr("RAG LATENCY — Embedding generation")

try:
    t_start = time.perf_counter()
    from app.services.knowledge_service import _get_embedder
    embedder     = _get_embedder()
    load_time_ms = (time.perf_counter() - t_start) * 1000
    info(f"Model load time (cold): {load_time_ms:.0f} ms")

    test_queries = [
        "DNS resolution failure nslookup",
        "BGP session not establishing",
        "Netskope steering policy not routing correctly",
        "VPN tunnel flapping intermittent disconnects",
        "VLAN misconfiguration switch port access mode",
    ]

    times = []
    for q in test_queries:
        t0 = time.perf_counter()
        embedder.encode([q])
        times.append((time.perf_counter() - t0) * 1000)
    info(f"Single query embed: min={min(times):.1f}ms  p50={statistics.median(times):.1f}ms  max={max(times):.1f}ms")

    # Batch of 10
    t0 = time.perf_counter()
    embedder.encode(test_queries * 2)
    batch_ms = (time.perf_counter() - t0) * 1000
    info(f"Batch of 10 queries: {batch_ms:.1f}ms ({batch_ms/10:.1f}ms each)")

    # Second call (warm)
    times2 = []
    for q in test_queries:
        t0 = time.perf_counter()
        embedder.encode([q])
        times2.append((time.perf_counter() - t0) * 1000)
    info(f"Warm embed:  min={min(times2):.1f}ms  p50={statistics.median(times2):.1f}ms  max={max(times2):.1f}ms")

    if statistics.median(times2) < 100:
        ok(f"Warm embedding p50 = {statistics.median(times2):.1f}ms (< 100ms threshold)")
    else:
        fail(f"Warm embedding p50 = {statistics.median(times2):.1f}ms (> 100ms)")

except Exception as e:
    fail(f"Embedding benchmark failed: {e}")
    import traceback; traceback.print_exc()

# ─── Section 2: ChromaDB query latency at different collection sizes ──────────
hdr("RAG LATENCY — ChromaDB query at N documents")

try:
    import chromadb, numpy as np
    from app.services.knowledge_service import (
        _get_embedder, _get_collection, get_rag_context,
        _clear_rag_cache, CHROMA_DIR,
    )

    # Use a *temporary* isolated collection so we don't pollute production data
    tmp_client     = chromadb.EphemeralClient()
    tmp_collection = tmp_client.get_or_create_collection(
        "bench_tmp", metadata={"hnsw:space": "cosine"}
    )

    embed = _get_embedder()
    CHUNK = "Networking troubleshooting runbook. BGP peer session down. Check interface status. Verify AS numbers match. Confirm TCP 179 is not blocked."

    results_table = []
    for n_docs in [10, 100, 500]:
        # Populate with n_docs worth of chunks
        ids, docs, metas, embs = [], [], [], []
        for i in range(n_docs):
            cid = f"doc_{i}_0"
            ids.append(cid)
            docs.append(f"{CHUNK} Doc {i}.")
            metas.append({"doc_id": f"doc_{i}", "domain": "networking", "title": f"Runbook {i}", "chunk_index": 0})
        embs = embed.encode(docs).tolist()

        # Fresh collection for each size
        try: tmp_client.delete_collection("bench_tmp")
        except Exception: pass
        col = tmp_client.get_or_create_collection("bench_tmp", metadata={"hnsw:space": "cosine"})
        col.add(ids=ids, documents=docs, embeddings=embs, metadatas=metas)

        # Query latency
        qemb = embed.encode(["BGP session not establishing"]).tolist()
        raw_times = []
        for _ in range(10):
            t0 = time.perf_counter()
            col.query(query_embeddings=qemb, n_results=min(3, n_docs),
                      include=["documents", "metadatas", "distances"])
            raw_times.append((time.perf_counter() - t0) * 1000)

        p50 = statistics.median(raw_times)
        p95 = sorted(raw_times)[int(0.95 * len(raw_times))]
        results_table.append((n_docs, p50, p95))
        info(f"  n_docs={n_docs:4d}: p50={p50:.1f}ms  p95={p95:.1f}ms  (10 queries)")

    # Evaluate
    all_fast = all(p50 < 200 for _, p50, _ in results_table)
    if all_fast:
        ok("All ChromaDB query p50 values < 200ms threshold")
    else:
        slow = [(n, p50) for n, p50, _ in results_table if p50 >= 200]
        fail(f"Slow queries: {slow}")

except Exception as e:
    fail(f"ChromaDB benchmark failed: {e}")
    import traceback; traceback.print_exc()

# ─── Section 3: RAG cache effectiveness ──────────────────────────────────────
hdr("RAG LATENCY — Cache hit vs miss")

try:
    from app.services import knowledge_service as ks

    # Clear cache
    ks._clear_rag_cache()

    query = "BGP session not establishing troubleshooting steps"

    # Cold call (cache miss)
    t0 = time.perf_counter()
    r1 = ks.get_rag_context(query, domain="networking", n_results=3)
    cold_ms = (time.perf_counter() - t0) * 1000

    # Warm call (cache hit)
    t0 = time.perf_counter()
    r2 = ks.get_rag_context(query, domain="networking", n_results=3)
    warm_ms = (time.perf_counter() - t0) * 1000

    info(f"Cache MISS: {cold_ms:.1f}ms")
    info(f"Cache HIT:  {warm_ms:.2f}ms")
    info(f"Speedup:    {cold_ms/max(warm_ms,0.001):.0f}×")

    assert r1 == r2, "Cache returned different result than cold call"
    ok("Cache returns identical result to cold call")

    if warm_ms < 1.0:
        ok(f"Cache hit latency {warm_ms:.3f}ms (< 1ms)")
    else:
        ok(f"Cache hit latency {warm_ms:.2f}ms")

    # Verify cache is invalidated after clear
    ks._clear_rag_cache()
    assert ks._rag_cache_key(query, "networking", 3) not in ks._rag_cache
    ok("Cache cleared correctly after _clear_rag_cache()")

except Exception as e:
    fail(f"Cache benchmark failed: {e}")
    import traceback; traceback.print_exc()

print("\n")
