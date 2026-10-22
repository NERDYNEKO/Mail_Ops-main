/** Hard guarantee: no dashes or exclamation marks survive in outgoing text. */
export function clean(text: string): string {
  return text
    .replace(/[—–]/g, ", ")
    .replace(/\s+-+\s+/g, ", ")
    .replace(/(?<=\w)-(?=\w)/g, " ")
    .replace(/ +,/g, ",")
    .replace(/,,/g, ",")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/!/g, ".")
    .trim();
}

export const firstName = (full?: string) => full?.trim().split(" ")[0] || "there";
