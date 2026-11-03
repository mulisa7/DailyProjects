import { run } from "./src/cli.ts";

if (import.meta.main) {
  const encoder = new TextEncoder();
  const code = await run(Deno.args, {
    out: (text) => Deno.stdout.writeSync(encoder.encode(text)),
    err: (text) => Deno.stderr.writeSync(encoder.encode(text)),
    readStdin: () => new Response(Deno.stdin.readable).text(),
  });
  Deno.exit(code);
}
