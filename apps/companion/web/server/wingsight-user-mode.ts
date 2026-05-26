import { resolve } from "node:path";

export function isWingsightUserMode(): boolean {
  return process.env.WINGSIGHT_MONTAGE_USER_MODE === "1";
}

function normalizeAddress(address: string): string {
  return address.trim().replace(/^\[|\]$/g, "").replace(/^::ffff:/i, "");
}

export function isLoopbackAddress(address: string): boolean {
  const addr = normalizeAddress(address);
  return addr === "127.0.0.1" || addr === "::1";
}

function isPrivateLanAddress(address: string): boolean {
  const addr = normalizeAddress(address);
  const parts = addr.split(".");
  if (parts.length === 4) {
    const octets = parts.map((part) => Number(part));
    if (octets.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) {
      return false;
    }
    const [a, b] = octets;
    return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }

  const lower = addr.toLowerCase();
  return lower.startsWith("fc") || lower.startsWith("fd") || lower.startsWith("fe80:");
}

export function isTrustedLocalAddress(address: string): boolean {
  if (isLoopbackAddress(address)) {
    return true;
  }
  return isWingsightUserMode() && isPrivateLanAddress(address);
}

export function getWingsightProjectDir(): string | null {
  const raw = process.env.WINGSIGHT_MONTAGE_PROJECT_DIR;
  if (!raw) return null;
  return resolve(raw);
}

export function getWingsightUploadsDir(): string | null {
  const projectDir = getWingsightProjectDir();
  if (!projectDir) return null;
  return resolve(projectDir, "projects", "uploads");
}
