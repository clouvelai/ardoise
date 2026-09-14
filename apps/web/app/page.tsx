import { Features } from "@/components/features";
import { Footer } from "@/components/footer";
import { Header } from "@/components/header";
import { Hero } from "@/components/hero";
import { Privacy } from "@/components/privacy";
import { Trust } from "@/components/trust";

export default function Home() {
  return (
    <div id="top" className="flex min-h-svh flex-col">
      <div className="flex min-h-svh flex-col">
        <Header />
        <Hero />
        <Trust />
      </div>
      <Features />
      <Privacy />
      <Footer />
    </div>
  );
}
