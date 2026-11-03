// Minimal assertions so the tests need no downloads.

export function assert(cond: unknown, msg = "assertion failed"): asserts cond {
  if (!cond) throw new Error(msg);
}

export function assertEquals<T>(actual: T, expected: T, msg = ""): void {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${msg ? msg + ": " : ""}expected ${e}, got ${a}`);
}

export function assertThrows(fn: () => unknown, _type: unknown, includes: string): void {
  try {
    fn();
  } catch (err) {
    if (!(err as Error).message.includes(includes)) {
      throw new Error(`error "${(err as Error).message}" does not include "${includes}"`);
    }
    return;
  }
  throw new Error("expected function to throw");
}
