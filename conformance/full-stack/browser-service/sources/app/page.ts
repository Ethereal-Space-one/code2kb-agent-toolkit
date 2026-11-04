export function buttonVisible(canExport: boolean): boolean {
  return canExport;
}
export function submit(send: (path: string, body: object) => unknown, requested: number) {
  return send("/gateway/reports", { requested });
}
