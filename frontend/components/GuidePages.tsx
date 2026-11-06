import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  BusFront,
  Headphones,
  MapPinned,
  Route,
  ShieldCheck,
} from "lucide-react";
import { ToolHeading } from "./TransportTools";
import PilotObservation from "./PilotObservation";

export function UserGuide() {
  return (
    <main>
      <ToolHeading
        title="User Guide"
        description="A few things to know before your first RushLess journey."
      />
      <div className="rl-guide-grid">
        <section className="rl-panel rl-guide-card">
          <span className="rl-service-icon mint">
            <Route size={24} />
          </span>
          <h2>Plan with a little more confidence.</h2>
          <ol>
            <li>
              Choose your starting stop and destination from the supported
              corridor.
            </li>
            <li>Compare Fastest and Comfortable recommendations.</li>
            <li>
              Open a journey to see the boarding crowd forecast, uncertainty
              range and stop sequence.
            </li>
            <li>
              Save the stop pair or watch the journey while the page stays open.
            </li>
          </ol>
          <Link href="/planner" className="rl-text-link">
            Open Journey Planner <ArrowRight size={15} />
          </Link>
        </section>
        <section className="rl-panel rl-guide-card">
          <span className="rl-service-icon blue">
            <BusFront size={24} />
          </span>
          <h2>Follow a bus or a route.</h2>
          <p>
            Track a Bus searches the active vehicles provided by the current
            source. Track a Live Route shows a directional stop pattern and its
            vehicles. No marker is shown when a position is missing or unusable.
          </p>
          <p style={{ marginTop: 12 }}>
            The Time Table separates scheduled arrivals from predicted arrivals.
            All schedule times use Asia/Kolkata.
          </p>
          <Link href="/track-bus" className="rl-text-link">
            Find a bus <ArrowRight size={15} />
          </Link>
        </section>
        <section className="rl-panel rl-guide-card">
          <span className="rl-service-icon violet">
            <ShieldCheck size={24} />
          </span>
          <h2>Understand what the data means.</h2>
          <p>
            Low crowding means below 40% of modeled capacity, Moderate means
            40–75%, and High means above 75%. These are illustrative thresholds,
            not official standards or a promise of seats.
          </p>
          <p style={{ marginTop: 12 }}>
            Unknown stays unknown. Confidence and heuristic ranges are not
            measured real-world accuracy. Insights shows source status, evidence
            and calibration readiness.
          </p>
          <Link href="/insights" className="rl-text-link">
            Explore data health <ArrowRight size={15} />
          </Link>
        </section>
        <section className="rl-panel rl-guide-card">
          <span className="rl-service-icon amber">
            <MapPinned size={24} />
          </span>
          <h2>Help the pilot learn.</h2>
          <p>
            Record an actual arrival or a crowd category only after safely
            stopping or boarding. Submit only actual events you have observed.
            Real pilot records need independently supported review before they
            become verified evidence.
          </p>
          <p style={{ marginTop: 12 }}>
            Do not include passenger identities, phone numbers, photographs or
            number plates.
          </p>
          <div style={{ marginTop: 18 }}>
            <PilotObservation />
          </div>
        </section>
      </div>
      <section className="rl-panel" style={{ marginTop: 22 }}>
        <h2 className="rl-tool-title">A few useful answers</h2>
        <details className="rl-faq">
          <summary>Is this the official BMTC app?</summary>
          <p>
            No. RushLess is an independent transport prototype. It is currently
            configured with a published BMTC network and has no genuine live
            BMTC connection. Always check the source status and actual operator
            information when travelling.
          </p>
        </details>
        <details className="rl-faq">
          <summary>Will journey alerts run after I close the page?</summary>
          <p>
            No. Watches run while the page is open. Saved alert preferences do
            not enable background push notifications. Reopen the planner and
            search again to check current departures.
          </p>
        </details>
        <details className="rl-faq">
          <summary>Are fares and facilities verified?</summary>
          <p>
            The Fare Calculator uses exact matching records from the published
            GTFS fare tables. It is not a guarantee of the current ticket price.
            Stop amenities such as shelter and step-free access have not been
            independently surveyed.
          </p>
        </details>
        <details className="rl-faq">
          <summary>Which parts are available in Kannada?</summary>
          <p>
            The language selector translates navigation, dashboard service
            labels and core tool labels. Advanced prediction, evidence and
            guidance text currently remains in English.
          </p>
        </details>
      </section>
    </main>
  );
}
export function Help() {
  return (
    <main>
      <ToolHeading
        title="Help & support"
        description="Find the right next step, from using the prototype to understanding your data."
      />
      <div className="rl-guide-grid">
        <section className="rl-panel rl-guide-card">
          <span className="rl-service-icon mint">
            <BookOpen size={24} />
          </span>
          <h2>New to RushLess?</h2>
          <p>
            Get a quick introduction to journey planning, vehicle tracking,
            predictions and the pilot observation form.
          </p>
          <Link href="/guide" className="rl-text-link">
            Read the User Guide <ArrowRight size={15} />
          </Link>
        </section>
        <section className="rl-panel rl-guide-card">
          <span className="rl-service-icon blue">
            <Headphones size={24} />
          </span>
          <h2>Need operator assistance?</h2>
          <p>
            This prototype does not operate a transport helpline or accept BMTC
            complaints. For tickets, lost property, service changes or safety
            assistance, use the operator’s verified channels or ask transport
            staff.
          </p>
          <div className="rl-operator-contact">
            <span>BMTC helpline</span>
            <a href="tel:+918022483777">080 2248 3777</a>
            <p>
              Listed in BMTC’s official app description. Contact availability
              may change.
            </p>
            <a
              className="rl-text-link"
              href="https://play.google.com/store/apps/details?id=com.bmtc.bmtcavls.two"
              target="_blank"
              rel="noreferrer"
            >
              View operator source <ArrowRight size={14} />
            </a>
          </div>
          <Link href="/feedback" className="rl-text-link">
            Write prototype feedback <ArrowRight size={15} />
          </Link>
        </section>
      </div>
      <section className="rl-panel rl-privacy" id="privacy">
        <h2 className="rl-tool-title">
          <ShieldCheck size={20} /> Your privacy & data
        </h2>
        <p>
          Your saved journeys, recent stop pairs and preferences use a random
          anonymous first-party cookie with server-side storage. No account,
          phone number or continuous device location is requested. Profiles
          expire after the configured inactive retention period, normally 30
          days.
        </p>
        <p>
          Use Saved journeys to clear recent searches or reset your anonymous
          profile. Feedback notes and language preferences live separately in
          browser storage. Clear feedback from its page or clear browser site
          data to remove those local settings.
        </p>
        <p>
          Pilot observations are a separate research record. Real records
          require review before they enter evaluation. Provider frames and pilot
          evidence are local prototype records; production retention and privacy
          processes still need review. Map tiles come from OpenStreetMap and
          require a network connection.
        </p>
        <Link href="/saved" className="rl-text-link" style={{ marginTop: 18 }}>
          Manage saved data <ArrowRight size={15} />
        </Link>
      </section>
    </main>
  );
}
