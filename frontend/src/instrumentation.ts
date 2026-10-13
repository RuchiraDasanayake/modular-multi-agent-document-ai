export async function register(): Promise<void> {
  // Passive recovery preserves copied run records; even periodic reconciliation
  // would mutate evidence without an explicit extraction request.
  if (process.env.IDPO_RECOVERY_READ_ONLY === "1") return;
  // Keep the import inside the Node branch so the Edge compiler excludes it.
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { startProductAutoRecoveryLoop } = await import("@/server/product-auto");
    startProductAutoRecoveryLoop();
  }
}
