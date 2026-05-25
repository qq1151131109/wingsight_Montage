import { resolve } from "node:path";

export function isWingsightUserMode(): boolean {
  return process.env.WINGSIGHT_MONTAGE_USER_MODE === "1";
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
