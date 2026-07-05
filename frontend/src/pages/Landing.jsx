import Hero from "../components/Hero";
import {
  Intro,
  TechMarquee,
  Benefits,
  Highlights,
  FinalCTA,
} from "../components/Sections";

export default function Landing() {
  return (
    <main id="top">
      <Hero />
      <Intro />
      <TechMarquee />
      <Benefits />
      <Highlights />
      <FinalCTA />
    </main>
  );
}
