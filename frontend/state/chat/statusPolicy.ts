const STATUS_NOISE_PATTERNS: RegExp[] = [
  /^Executing:/i,
  /^Step\s+\d+:\s+.+\s+running\.{0,3}$/i,
  /^Step\s+\d+:\s+.+\s+completed\.{0,3}$/i,
];

const STATUS_PRIORITY_PATTERNS: RegExp[] = [
  /initializing/i,
  /planning/i,
  /synthesizing|synthesis/i,
  /verifying|verification/i,
  /compliance/i,
  /failed|error|crashed/i,
];

export function shouldDisplayStatus(message: string): boolean {
  const isPriority = STATUS_PRIORITY_PATTERNS.some((pattern) => pattern.test(message));
  if (isPriority) return true;
  return !STATUS_NOISE_PATTERNS.some((pattern) => pattern.test(message));
}
