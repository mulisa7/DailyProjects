// Lists every file and folder under a root as "/"-separated relative paths.
// Symlinks are listed but never followed.

export interface Listing {
  paths: string[];
  errors: string[];
}

export async function listTree(root: string): Promise<Listing> {
  const paths: string[] = [];
  const errors: string[] = [];
  const stack: string[] = [""];

  while (stack.length > 0) {
    const rel = stack.pop()!;
    const dir = rel === "" ? root : root.replace(/[\\/]+$/, "") + "/" + rel;
    try {
      for await (const entry of Deno.readDir(dir)) {
        const childRel = rel === "" ? entry.name : rel + "/" + entry.name;
        paths.push(childRel);
        if (entry.isDirectory && !entry.isSymlink) stack.push(childRel);
      }
    } catch (err) {
      errors.push(`cannot read ${dir}: ${(err as Error).message}`);
    }
  }
  return { paths, errors };
}
