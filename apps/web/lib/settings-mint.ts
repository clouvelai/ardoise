/**
 * Settings mint chrome: token is shown once. Copy the raw token or the
 * prefilled login command. Never persist prompts or credentials.
 */

export const SETTINGS_COPY = {
  copyToken: "Copy token",
  copyLogin: "Copy login command",
  copied: "Copied",
  thenSync: "then ardoise sync",
} as const;

export function loginCommand(token: string): string {
  return `ardoise login --token ${token}`;
}

export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}
