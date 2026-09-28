"""What an offer will do, before the owner runs it, and which offer to run.

An offer is a discount for a window of the day, for at most `cap` customers. Two groups use it:
- new customers it brings, who would not have come: they grow with the discount (RESPONSE);
- customers who would have come anyway and now pay less (TAKE_UP). This is the cost most owners never see.
The cap limits both together. For each offer Bluedip shows the customers it brings, the change in revenue, and the
change in margin after food cost: an offer can raise revenue and still lose money.

RESPONSE and TAKE_UP start as stated assumptions and are learned from each restaurant's finished offers (learn).
The CEO's rule on record: no offer deeper than 50%, and none that takes the bill below its food cost.
"""
from __future__ import annotations

RESPONSE = 1.2  # new customers per unit of discount, as a share of the covers expected anyway (starting assumption)
TAKE_UP = 0.3  # share of the covers expected anyway that use the offer (starting assumption)
PRIOR_WEIGHT = 3  # the starting assumption counts as three finished offers until real ones outweigh it
MAX_DISCOUNT = 0.5  # the CEO's rule
DISCOUNTS = [round(0.05 * i, 2) for i in range(1, 11)]  # 5% to 50%
MIN_GAIN = 100  # rupees of margin: below this an offer is not worth the owner's attention


class OfferError(ValueError):
    """An offer Bluedip refuses: a bad window, discount or cap, or one that breaks the CEO's rule."""


def check(start: int, end: int, discount: float, cap: int, restaurant: dict) -> None:
    if not restaurant["open"] <= start < end <= restaurant["close"]:
        raise OfferError(f"the window must fall within opening hours, {restaurant['open']}:00 to {restaurant['close']}:00")
    if not 0 < discount <= MAX_DISCOUNT:
        raise OfferError("the discount must be more than 0% and at most 50% (the rule on record)")
    if discount > 1 - restaurant["food_cost"]:
        raise OfferError("this discount takes the bill below its food cost (the rule on record)")
    if not 1 <= cap <= restaurant["seats"] * (end - start):
        raise OfferError("the cap must be at least 1 customer and no more than the seats in the window")


def estimate(expected: float, discount: float, cap: int, restaurant: dict, response: float = RESPONSE,
             take_up: float = TAKE_UP) -> dict:
    """expected: covers expected in the window without an offer."""
    bill, food = restaurant["avg_bill"], restaurant["food_cost"]
    new_demand = expected * response * discount
    anyway_demand = expected * take_up
    wanting = new_demand + anyway_demand
    used = wanting
    new = used * new_demand / wanting if wanting else 0.0
    anyway = used - new
    return {"expected_without": round(expected, 1), "customers_using": round(used, 1), "new_customers": round(new, 1),
            "would_have_come_anyway": round(anyway, 1), "cap_reached": wanting > cap,
            "revenue_change": round(new * bill * (1 - discount) - anyway * bill * discount),
            "margin_change": round(new * bill * (1 - discount - food) - anyway * bill * discount),
            "assumptions": {"response": round(response, 3), "take_up": take_up, "avg_bill": bill,
                            "food_cost": food, "food_cost_assumed": restaurant.get("food_cost_assumed", False)}}


def best(expected: float, cap: int, restaurant: dict, response: float = RESPONSE) -> dict | None:
    """The discount that adds the most margin in this window, within the CEO's rule; None when every offer loses
    money, because then the honest recommendation is no offer."""
    options = []
    for d in DISCOUNTS:
        try:
            check(restaurant["open"], restaurant["close"], d, cap, restaurant)
        except OfferError:
            continue
        options.append((estimate(expected, d, cap, restaurant, response), d))
    options = [o for o in options if o[0]["margin_change"] > 0]
    if not options:
        return None
    e, d = max(options, key=lambda o: (o[0]["margin_change"], -o[1]))
    return {"discount": d, "cap": cap, **e}


def recommend(expected_by_slot: list[dict], restaurant: dict, response: float = RESPONSE) -> list[dict]:
    """One recommendation per meal: its quiet window and the best offer for it, or why there is none."""
    out = []
    for s in expected_by_slot:
        q = s.get("quiet")
        if not q:
            out.append({"slot": s["slot"], "window": None, "offer": None, "why": "No quiet hours: no offer needed."})
            continue
        exp = s["quiet_covers"]
        cap = max(1, round(exp))  # enough for about as many customers again as the window expects
        o = best(exp, cap, restaurant, response)
        if o and o["margin_change"] < MIN_GAIN:
            out.append({"slot": s["slot"], "window": q, "offer": None,
                        "why": f"Too few customers in these hours: the best offer adds under ₹{MIN_GAIN} of margin."})
            continue
        out.append({"slot": s["slot"], "window": q, "offer": o,
                    "why": "The discount that adds the most margin in the quiet hours." if o else
                           "Every discount here would lose money: the customers it brings do not pay for the ones "
                           "who would have come anyway."})
    return out


def learn(observed: list[float], prior: float = RESPONSE) -> float:
    """The response estimate after the restaurant's finished offers: the starting assumption, weighed as
    PRIOR_WEIGHT offers, averaged with what each finished offer showed."""
    return (prior * PRIOR_WEIGHT + sum(observed)) / (PRIOR_WEIGHT + len(observed))


def observed_response(expected: float, actual: int, discount: float) -> float:
    """What a finished offer showed: the covers above those expected, per unit of discount."""
    if expected <= 0 or discount <= 0:
        return 0.0
    return max(0.0, actual - expected) / (expected * discount)
