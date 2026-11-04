def find_order(user, order_id, orders):
    if not user["signed_in"]:
        return {"error": "sign_in_required"}
    order = orders.get(order_id)
    if order is None:
        return {"error": "not_found"}
    if order["region"] not in user["regions"]:
        return {"error": "outside_region"}
    return {"order": order}
