export async function register(): Promise<void> {
  // Keep the import inside the Node branch so the Edge compiler excludes it.
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { startProductAutoRecoveryLoop } = await import("@/server/product-auto");
    startProductAutoRecoveryLoop();
  }
}
