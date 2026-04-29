def build(supplier: str, product_type: str, variant_id: str, prints: list[dict]) -> str:
    """
    Build a supplier_reference string from the selected variant and print options.
    Format is supplier-specific and may also vary by product_type (e.g. clothing vs gifts).
    """
    if supplier == "mko":
        return _mko(variant_id, prints)
    if supplier == "xdc":
        return _xdc(variant_id, prints)
    raise ValueError(f"No supplier_reference builder registered for supplier: {supplier!r}")


def _mko(variant_id: str, prints: list[dict]) -> str:
    # No print: variant_id only
    # With print: variant_id__teccode#areacode[__teccode#areacode ...]
    if not prints:
        return variant_id
    parts = "__".join(f"{p['teccode']}#{p['areacode']}" for p in prints)
    return f"{variant_id}__{parts}"


def _xdc(variant_id: str, prints: list[dict]) -> str:
    # No print: variant_id only
    # With print: variant_id__technique#position[__technique#position ...]
    if not prints:
        return variant_id
    parts = "__".join(f"{p['teccode']}#{p['areacode']}" for p in prints)
    return f"{variant_id}__{parts}"
