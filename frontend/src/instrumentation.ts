export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { startProductAutoRecoveryLoop } = await import("@/server/product-auto");
  startProductAutoRecoveryLoop();
}
