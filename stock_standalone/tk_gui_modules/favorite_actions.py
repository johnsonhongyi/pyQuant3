"""Submit favorite-store writes and poll their completion on the Tk UI thread."""

import logging

logger = logging.getLogger(__name__)


def _run_manager_action(method_name, args, kwargs):
    from global_favorites import GlobalFavoriteManager

    manager = GlobalFavoriteManager()
    result = getattr(manager, method_name)(*args, **kwargs)
    if result == "error" or (isinstance(result, dict) and result.get("persisted") is False):
        raise RuntimeError("favorite_write_failed")
    return result


def _set_status(owner, message, is_error=False):
    try:
        for attribute in ("status_var", "status_var2"):
            variable = getattr(owner, attribute, None)
            if variable is not None and hasattr(variable, "set"):
                variable.set(message[:180])
                return
        label = getattr(owner, "lbl_status", None)
        if label is not None and hasattr(label, "config"):
            label.config(text=message[:180], fg="firebrick" if is_error else "darkgreen")
    except Exception:
        logger.debug("Could not display favorite-write status", exc_info=True)


def submit_tk_favorite_action(owner, method_name, *args, after_target=None,
                              on_complete=None, success_message=None, **kwargs):
    """Submit a write without calling Tk from the worker; poll the Future via ``after``."""
    from global_favorites import submit_favorite_write

    target = after_target or getattr(owner, "root", owner)
    future = submit_favorite_write(_run_manager_action, method_name, args, kwargs)

    def poll_result():
        try:
            if hasattr(target, "winfo_exists") and not target.winfo_exists():
                return
            if not future.done():
                target.after(40, poll_result)
                return
            try:
                result, error = future.result(), None
            except Exception as caught:
                result, error = None, caught
            if error is None:
                rejected = result.get("rejected") or [] if isinstance(result, dict) else []
                message = success_message or "重点关注已保存"
                if rejected:
                    message += f"，{len(rejected)} 只未处理"
            else:
                message = "重点关注保存失败: " + str(error)
            _set_status(owner, message, error is not None)
            if on_complete is not None:
                on_complete(owner, result, error)
        except Exception:
            logger.debug("Tk favorite completion polling stopped", exc_info=True)

    try:
        target.after(40, poll_result)
    except Exception:
        logger.debug("Could not schedule Tk favorite completion", exc_info=True)
    return future
