import crypto from "node:crypto";

/**
 * Derives a deterministic token/password from conversationId and salt.
 * 
 * ARCHITECTURE:
 * - Each conversation has a unique salt stored only in the database
 * - Tokens are derived deterministically: hash(conversationId + salt)
 * - Clients never see the salt - they only receive the derived token/password
 * - Even if someone knows the conversationId, they cannot derive the token without the salt
 * 
 * For editor access, we append ":editor" to the salt before hashing
 * This creates a different password for editor vs owner role using the same salt
 */
export function deriveToken(conversationId: string, salt: string): string {
  const combined = `${conversationId}:${salt}`;
  return crypto.createHash("sha256").update(combined).digest("hex");
}
