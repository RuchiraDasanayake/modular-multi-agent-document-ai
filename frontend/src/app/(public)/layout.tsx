import { PublicNavbar } from "@/components/public-navbar";
import { Footer } from "@/components/footer";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <PublicNavbar />
            <main className="pt-16 lg:pt-20">{children}</main>
            <Footer />
        </>
    );
}
