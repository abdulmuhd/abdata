// Receipt viewer: opens a transaction by reference from the API.
import { get } from "../api.js";
import { showResult } from "../ui.js";

export async function openReceipt(reference, { onDone } = {}) {
  try {
    const txn = await get(`/transactions/${encodeURIComponent(reference)}`);
    showResult({ txn, onDone });
  } catch (err) {
    const { toast } = await import("../ui.js");
    toast(err.message, "err");
  }
}
