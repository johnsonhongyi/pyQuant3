import os
import pandas as pd

from JSONData import tdx_hdf5_api as h5a


def test_schema_self_heal_preserves_sibling_tables(tmp_path, monkeypatch):
    target = tmp_path / "tdx_last_df.h5"
    with pd.HDFStore(target, mode="w") as store:
        store.put("low_d_120_y_all", pd.DataFrame({"lastp": [10.0]}, index=["000001"]), format="table")
        store.put("low_w_300_y_all", pd.DataFrame({"lastp": [20.0]}, index=["000001"]), format="table")

    real_get = h5a.cct.get_ramdisk_path
    monkeypatch.setattr(h5a.cct, "get_ramdisk_path", lambda name: str(target) if str(name).startswith("tdx_last_df") else real_get(name))

    original_put = h5a.put_table_safe
    calls = {"n": 0}
    def flaky_put(store, table, df, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("cannot match existing table structure")
        return original_put(store, table, df, **kwargs)
    monkeypatch.setattr(h5a, "put_table_safe", flaky_put)

    new_df = pd.DataFrame({"lastp": [11.0]}, index=["000001"])
    result = h5a.write_hdf_db(
        "tdx_last_df",
        new_df,
        table="low_d_120_y_all",
        append=False,
        MultiIndex=False,
    )

    with pd.HDFStore(target, mode="r") as store:
        keys = set(store.keys())
        assert "/low_d_120_y_all" in keys
        assert "/low_w_300_y_all" in keys
        assert float(store["low_w_300_y_all"].iloc[0]["lastp"]) == 20.0
