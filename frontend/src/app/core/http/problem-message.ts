// Dependency-free so the node test runner can import it (tests/auth-errors.test.mjs).

/** The API's problem+json error body (see ApiProblem). */
interface Problem { detail?: string; errors?: unknown }

interface FieldError { loc?: (string | number)[]; msg?: string; type?: string }

/**
 * The message to show for a failed request. A 422 says only "Request
 * validation failed." in `detail`; the reason the person can act on ("This
 * password is too common…", "Enter a valid email address") is in `errors[]`.
 */
export function problemMessage(err: unknown, fallback: string): string {
  const http = err as { status?: number; error?: Problem } | null;
  if (http?.status === 0) return 'Cannot reach the server. Check your connection.';
  const problem = http?.error;
  if (http?.status === 429) {
    const wait = (problem?.errors as { retry_after?: number } | undefined)?.retry_after;
    if (wait) return `Too many attempts. Please wait ${wait < 90 ? `${wait} seconds` : `${Math.ceil(wait / 60)} minutes`} and try again.`;
  }
  const first = Array.isArray(problem?.errors) ? (problem!.errors as FieldError[])[0] : undefined;
  if (first?.msg) return fieldMessage(first);
  return problem?.detail || fallback;
}

function fieldMessage(error: FieldError): string {
  const field = [...(error.loc ?? [])].reverse().find((part): part is string => typeof part === 'string' && part !== 'body');
  const label = field ? field.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase()) : '';
  const msg = error.msg!.replace(/^Value error, /, '');
  if (error.type === 'missing') return label ? `${label} is required.` : 'Some details are missing.';
  if (msg.startsWith('value is not a valid email address')) {
    return `Enter a valid email address${msg.includes(':') ? ` (${msg.split(':').slice(1).join(':').trim().replace(/\.$/, '')})` : ''}.`;
  }
  if (error.type === 'json_invalid' || error.type === 'model_attributes_type') return 'Something went wrong sending the form. Please try again.';
  // pydantic's own wording ("String should have at least 2 characters") needs the field name.
  return error.type === 'value_error' || !label ? msg : `${label}: ${msg}`;
}
