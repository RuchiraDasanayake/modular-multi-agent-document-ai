import Cookies from "js-cookie";

const TOKEN_KEY = "ahmn_token";

const isProduction = typeof window !== "undefined" && window.location.protocol === "https:";

export function getToken(): string | undefined {
  return Cookies.get(TOKEN_KEY);
}

export function setToken(token: string): void {
  Cookies.set(TOKEN_KEY, token, {
    expires: 1,
    sameSite: "Lax",
    secure: isProduction,
    path: "/",
  });
}

export function removeToken(): void {
  Cookies.remove(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
