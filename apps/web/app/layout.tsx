import "./globals.css";
import type { ReactNode } from "react";
import FreshnessBadge from "@/components/FreshnessBadge";

export const metadata = {
  title: "KOSPI Investor Flow",
  description: "개인/기관/외국인 순매수 tracking, screeners, and ML projections",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <nav>
          <strong>KOSPI Flow</strong>
          <a href="/">개요</a>
          <a href="/rankings">순매수 랭킹</a>
          <a href="/screener">스크리너</a>
          <a href="/watchlists">관심종목</a>
          <a href="/models">모델</a>
          <a href="/data-status">데이터 상태</a>
          <span
            style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}
          >
            <FreshnessBadge />
            <form action="/search" method="get">
              <input type="search" name="q" placeholder="종목 검색…" aria-label="종목 검색" />
            </form>
          </span>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
