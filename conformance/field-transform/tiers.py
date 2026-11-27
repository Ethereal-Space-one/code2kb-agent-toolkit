"""Synthetic in-memory tiers. No configuration load, writes or real business rules."""
from collections import namedtuple

Tier = namedtuple("Tier", "name lower estimate upper")
BASE = (Tier("小档", 0, 3, 5), Tier("大档", 5, 7, 10))


def adjusted(tier, d):
    if d <= 0:
        return tier
    lower = tier.lower + d if tier.lower > 0 else tier.lower
    estimate = tier.estimate + 2 * d if tier.estimate <= 7 else tier.estimate
    upper = tier.upper - d if tier.upper >= 5 else tier.upper
    return Tier(tier.name, lower, estimate, upper)


def select(weight, d):
    for tier in (adjusted(tier, d) for tier in BASE):
        if tier.lower < weight <= tier.upper:
            return tier.name, "命中"
        if weight <= tier.lower:
            return tier.name, "向后取档"
    return None, "超最大档"
