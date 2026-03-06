from math import comb
import random


def contingency_table(scores_a, scores_b):
    if len(scores_a) != len(scores_b):
        raise ValueError(
            f"Score vectors must have same length: {len(scores_a)} vs {len(scores_b)}"
        )

    both_correct = sum(1 for a, b in zip(scores_a, scores_b) if a == 1 and b == 1)
    only_a = sum(1 for a, b in zip(scores_a, scores_b) if a == 1 and b == 0)
    only_b = sum(1 for a, b in zip(scores_a, scores_b) if a == 0 and b == 1)
    both_wrong = sum(1 for a, b in zip(scores_a, scores_b) if a == 0 and b == 0)

    return {
        "both_correct": both_correct,
        "only_a": only_a,
        "only_b": only_b,
        "both_wrong": both_wrong,
        "n_discordant": only_a + only_b,
        "n_total": len(scores_a),
    }



def bootstrap_ci(scores_a, scores_b, n_bootstrap=10000, confidence=0.95, seed=42):
    if len(scores_a) != len(scores_b):
        raise ValueError(
            f"Score vectors must have same length: {len(scores_a)} vs {len(scores_b)}"
        )

    n = len(scores_a)
    observed_delta = sum(scores_a) / n - sum(scores_b) / n

    rng = random.Random(seed)
    deltas = []
    for _ in range(n_bootstrap):
        indices = [rng.randint(0, n - 1) for _ in range(n)]
        mean_a = sum(scores_a[i] for i in indices) / n
        mean_b = sum(scores_b[i] for i in indices) / n
        deltas.append(mean_a - mean_b)

    deltas.sort()
    alpha = 1 - confidence
    lo = deltas[int(n_bootstrap * alpha / 2)]
    hi = deltas[int(n_bootstrap * (1 - alpha / 2))]

    return {
        "delta": observed_delta,
        "ci_lower": lo,
        "ci_upper": hi,
        "confidence": confidence,
    }
    

def mcnemar_test(scores_a, scores_b):
    table = contingency_table(scores_a, scores_b)
    b = table["only_a"]
    c = table["only_b"]
    n = b + c

    if n == 0:
        return {"p_value": 1.0, "significant": False, "winner": None}

    k = min(b, c)
    p_value = 2 * sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    p_value = min(p_value, 1.0)

    winner = None
    if p_value < 0.05:
        winner = "a" if b > c else "b"

    return {
        "p_value": p_value,
        "significant": p_value < 0.05,
        "winner": winner,
    }
    
    
    
def compare_models_stats(scores_a, scores_b):
    table = contingency_table(scores_a, scores_b)
    mcnemar = mcnemar_test(scores_a, scores_b)
    ci = bootstrap_ci(scores_a, scores_b)

    return {
        "contingency": table,
        "mcnemar": mcnemar,
        "bootstrap": ci,
        "mean_a": sum(scores_a) / len(scores_a),
        "mean_b": sum(scores_b) / len(scores_b),
    }