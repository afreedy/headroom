export function remaining(window) {
  return window && typeof window.usedPercent === 'number' && Number.isFinite(window.usedPercent) ? Math.max(0, Math.min(100, 100 - window.usedPercent)) : null;
}
export function resetText(timestamp, now = Date.now()) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return 'Reset time unavailable';
  const delta = timestamp * 1000 - now;
  if (delta <= 0) return 'Reset passed · refresh to confirm';
  const mins = Math.ceil(delta / 60000), hours = Math.floor(mins / 60), days = Math.floor(hours / 24);
  return days ? `${days}d ${hours % 24}h` : hours ? `${hours}h ${mins % 60}m` : `${mins}m`;
}
export function duration(mins) {
  if (!Number.isFinite(mins) || mins <= 0) return 'Usage window';
  return mins % 1440 === 0 ? `${mins / 1440}-day limit` : mins % 60 === 0 ? `${mins / 60}-hour limit` : `${mins}-minute limit`;
}
export function stale(account, now = Date.now()) { return !account.updatedAt || now - account.updatedAt * 1000 > 5 * 60 * 1000; }
export function eligible(account, now = Date.now()) {
  const windows = Object.values(account.buckets || {}).flatMap(b => b ? [b.primary,b.secondary].filter(Boolean) : []);
  return !account.error && !stale(account,now) && windows.length > 0 && windows.every(w => remaining(w) !== null && remaining(w) > 0 && (!w.resetsAt || w.resetsAt*1000 > now));
}

export function expiryText(timestamp, now = Date.now()) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return 'Expiry not provided';
  if (timestamp * 1000 <= now) return 'Expired · refresh to confirm';
  return resetText(timestamp, now) + ' left';
}

export function freshReading(account, connected, now = Date.now()) {
  return connected && !account.error && !account.needsLogin && !stale(account, now);
}

export function currentWindow(window, now = Date.now()) {
  return window?.resetsAt && window.resetsAt * 1000 <= now ? {...window, usedPercent: null} : window;
}
