"use client";
import { createContext, useContext, useEffect, useState } from "react";
const kannada: Record<string, string> = {
  Overview: "ಅವಲೋಕನ",
  "Journey Planner": "ಪ್ರಯಾಣ ಯೋಜನೆ",
  "Best Route Explorer": "ಉತ್ತಮ ಮಾರ್ಗ ಅನ್ವೇಷಣೆ",
  "Track a Bus": "ಬಸ್ ಪತ್ತೆಹಚ್ಚಿ",
  "Track a Live Route": "ಮಾರ್ಗ ಪತ್ತೆಹಚ್ಚಿ",
  "Time Table": "ವೇಳಾಪಟ್ಟಿ",
  Facilities: "ಸೌಲಭ್ಯಗಳು",
  "Fare Calculator": "ದರ ಲೆಕ್ಕಾಚಾರ",
  Feedback: "ಪ್ರತಿಕ್ರಿಯೆ",
  "User Guide": "ಬಳಕೆದಾರರ ಮಾರ್ಗದರ್ಶಿ",
  "Saved journeys": "ಉಳಿಸಿದ ಪ್ರಯಾಣಗಳು",
  "Corridor insights": "ಮಾರ್ಗದ ಮಾಹಿತಿ",
  "Help & support": "ಸಹಾಯ ಮತ್ತು ಬೆಂಬಲ",
  "Your commute": "ನಿಮ್ಮ ಪ್ರಯಾಣ",
  "Explore & more": "ಇನ್ನಷ್ಟು ಅನ್ವೇಷಿಸಿ",
  Bengaluru: "ಬೆಂಗಳೂರು",
  "Your city. Your journey.": "ನಿಮ್ಮ ನಗರ. ನಿಮ್ಮ ಪ್ರಯಾಣ.",
  "A little less rush starts here.": "ನೆಮ್ಮದಿಯ ಪ್ರಯಾಣ ಇಲ್ಲಿಂದ ಆರಂಭ.",
  "Less waiting.": "ಕಾಯುವಿಕೆ ಕಡಿಮೆ.",
  "More living.": "ಬದುಕಿಗೆ ಹೆಚ್ಚು ಸಮಯ.",
  "Know your bus before you board. Plan a calmer journey across Bengaluru’s Outer Ring Road.":
    "ಬಸ್ ಹತ್ತುವ ಮೊದಲೇ ಮಾಹಿತಿ ಪಡೆಯಿರಿ. ಬೆಂಗಳೂರಿನ ಹೊರ ವರ್ತುಲ ರಸ್ತೆಯಲ್ಲಿ ನೆಮ್ಮದಿಯ ಪ್ರಯಾಣ ಯೋಜಿಸಿ.",
  From: "ಇಂದ",
  To: "ಗೆ",
  "Find my journey": "ಪ್ರಯಾಣ ಹುಡುಕಿ",
  "Everything for your next ride": "ನಿಮ್ಮ ಮುಂದಿನ ಪ್ರಯಾಣಕ್ಕೆ ಎಲ್ಲವೂ",
  "Choose a service and get moving.": "ಸೇವೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿ, ಪ್ರಯಾಣ ಆರಂಭಿಸಿ.",
  "Compare arrivals and crowding": "ಆಗಮನ ಮತ್ತು ಜನಸಂದಣಿ ಹೋಲಿಸಿ",
  "Find a vehicle on the corridor": "ಮಾರ್ಗದಲ್ಲಿ ಬಸ್ ಹುಡುಕಿ",
  "Explore stops and route activity": "ನಿಲ್ದಾಣ ಮತ್ತು ಮಾರ್ಗದ ಚಟುವಟಿಕೆ",
  "See upcoming stop arrivals": "ಮುಂದಿನ ಆಗಮನಗಳನ್ನು ನೋಡಿ",
  "Explore the supported stop directory": "ನಿಲ್ದಾಣಗಳ ಪಟ್ಟಿ ನೋಡಿ",
  "Estimate your journey budget": "ಪ್ರಯಾಣ ವೆಚ್ಚ ಅಂದಾಜಿಸಿ",
  "Save and export your suggestions": "ಸಲಹೆಗಳನ್ನು ಉಳಿಸಿ ರಫ್ತು ಮಾಡಿ",
  "Get to know RushLess": "ರಶ್‌ಲೆಸ್ ಬಗ್ಗೆ ತಿಳಿಯಿರಿ",
  "Your everyday journeys": "ನಿಮ್ಮ ದೈನಂದಿನ ಪ್ರಯಾಣಗಳು",
  "View all": "ಎಲ್ಲವನ್ನೂ ನೋಡಿ",
  "On the corridor": "ಮಾರ್ಗದಲ್ಲಿ",
  "Data you can understand": "ಪಾರದರ್ಶಕ ಮಾಹಿತಿ",
  "Open insights": "ಮಾಹಿತಿ ತೆರೆಯಿರಿ",
  "Demo simulation": "ಪ್ರಾತ್ಯಕ್ಷಿಕೆ ಅನುಕರಣೆ",
  "No live BMTC connection": "ನೇರ ಬಿಎಂಟಿಸಿ ಸಂಪರ್ಕವಿಲ್ಲ",
  "Plan a journey": "ಪ್ರಯಾಣ ಯೋಜಿಸಿ",
  "No journeys saved yet.": "ಇನ್ನೂ ಪ್ರಯಾಣ ಉಳಿಸಿಲ್ಲ.",
  "Save a stop pair in the planner to keep it here.":
    "ಯೋಜನೆಯಲ್ಲಿ ನಿಲ್ದಾಣ ಜೋಡಿಯನ್ನು ಉಳಿಸಿ.",
  "Supported stops": "ಬೆಂಬಲಿತ ನಿಲ್ದಾಣಗಳು",
  "Route patterns": "ಮಾರ್ಗಗಳು",
  "Active vehicles": "ಸಕ್ರಿಯ ವಾಹನಗಳು",
  "Demo vehicles": "ಪ್ರಾತ್ಯಕ್ಷಿಕೆ ವಾಹನಗಳು",
  Menu: "ಮೆನು",
  "Close menu": "ಮೆನು ಮುಚ್ಚಿ",
  "Independent transport prototype": "ಸ್ವತಂತ್ರ ಸಾರಿಗೆ ಮಾದರಿ",
  Search: "ಹುಡುಕಿ",
  Route: "ಮಾರ್ಗ",
  "Select a stop": "ನಿಲ್ದಾಣ ಆಯ್ಕೆಮಾಡಿ",
  "All routes": "ಎಲ್ಲಾ ಮಾರ್ಗಗಳು",
  Updated: "ನವೀಕರಿಸಲಾಗಿದೆ",
  "Explore the corridor": "ಮಾರ್ಗ ಅನ್ವೇಷಿಸಿ",
};
type LocaleContext = {
  language: "en" | "kn";
  setLanguage: (language: "en" | "kn") => void;
  t: (text: string) => string;
};
const Context = createContext<LocaleContext>({
  language: "en",
  setLanguage: () => {},
  t: (text) => text,
});
export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [language, update] = useState<"en" | "kn">("en");
  useEffect(() => {
    try {
      if (localStorage.getItem("rushless-language-v1") === "kn") update("kn");
    } catch {
      /* English remains available without storage. */
    }
  }, []);
  function setLanguage(value: "en" | "kn") {
    update(value);
    try {
      localStorage.setItem("rushless-language-v1", value);
    } catch {
      /* Keep the selection for this visit. */
    }
  }
  return (
    <Context.Provider
      value={{
        language,
        setLanguage,
        t: (text) => (language === "kn" ? kannada[text] || text : text),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export const useLocale = () => useContext(Context);
