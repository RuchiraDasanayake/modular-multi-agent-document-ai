import type { ProductAutoRun } from "@/types/product-auto";

/** Keep list reads from replacing a run admitted after their snapshot began. */
export class ProductAutoRunRefresh {
  private generation = 0;
  private pending: Promise<ProductAutoRun[]> | null = null;
  private admissions = 0;

  constructor(private readonly apply: (runs: ProductAutoRun[]) => void,
    private readonly busy: (busy: boolean) => void) {}

  invalidate(): void {
    this.generation += 1;
    this.pending = null;
  }

  beginAdmission(): () => void {
    this.admissions += 1;
    this.invalidate();
    this.busy(false);
    let finished = false;
    return () => {
      if (finished) return;
      finished = true;
      this.admissions -= 1;
      this.invalidate();
      this.busy(false);
    };
  }

  async refresh(load: () => Promise<ProductAutoRun[]>, onCurrent?: (runs: ProductAutoRun[]) => void): Promise<void> {
    if (this.admissions > 0) return;
    const generation = this.generation;
    const pending = this.pending ?? load();
    this.pending = pending;
    this.busy(true);
    try {
      const runs = await pending;
      if (generation === this.generation) {
        this.apply(runs);
        onCurrent?.(runs);
      }
    } catch (error) {
      if (generation === this.generation) throw error;
    } finally {
      if (generation === this.generation && this.pending === pending) {
        this.pending = null;
        this.busy(false);
      }
    }
  }
}
