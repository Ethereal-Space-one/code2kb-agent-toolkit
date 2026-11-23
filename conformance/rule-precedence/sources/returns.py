"""Synthetic library return desk. Produce a plan, not a physical transfer."""


def plan_return(*, reserved: bool, damaged: bool):
    notes = ("check-hold",) if reserved else ()
    if damaged:
        return "repair", notes
    if reserved:
        return "hold-shelf", notes
    return "open-shelf", notes
