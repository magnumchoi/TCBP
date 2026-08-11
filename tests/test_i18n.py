def test_en_catalog_complete():
    from messages import ko, en
    missing = set(ko.MESSAGES) - set(en.MESSAGES)
    assert not missing, f"en is missing keys: {sorted(missing)}"


def test_ko_catalog_complete():
    from messages import ko, en
    orphan = set(en.MESSAGES) - set(ko.MESSAGES)
    assert not orphan, f"en has orphan keys not in ko: {sorted(orphan)}"
