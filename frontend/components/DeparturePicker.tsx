"use client";
import { useEffect,useState } from "react";
import { Clock3 } from "lucide-react";
import { istParts,istIso } from "./departureTime";
export { istParts,istIso } from "./departureTime";
export default function DeparturePicker({value,onChange}:{value:string;onChange:(s:string)=>void}) {
  const [current,setCurrent]=useState<Date|null>(null);
  useEffect(()=>{setCurrent(new Date());const timer=setInterval(()=>setCurrent(new Date()),30000);return()=>clearInterval(timer);},[]);
  const now=current?istParts(current):{date:"",time:""};
  const tomorrow=current?istParts(new Date(current.getTime()+86400000)):now;
  const max=current?istParts(new Date(current.getTime()+30*86400000)):now;
  const [date,time]=value?value.split("T"):[now.date,now.time];
  const presets=current?[
    {label:"Today, 8:30 AM",value:now.date+"T08:30"},
    {label:"Today, 6:00 PM",value:now.date+"T18:00"},
    {label:"Tomorrow, 8:30 AM",value:tomorrow.date+"T08:30"},
  ].filter(p=>new Date(istIso(p.value)).getTime()>current.getTime()):[];
  return <div className="rl-departure-picker">
    <div className="rl-departure-title"><Clock3 size={15}/><strong>Departure</strong><span>IST · Bengaluru time</span></div>
    <div className="rl-departure-presets"><button type="button" aria-pressed={!value} onClick={()=>onChange("")}>Leave now</button>{presets.map(p=><button type="button" key={p.value} aria-pressed={value===p.value} onClick={()=>onChange(p.value)}>{p.label}</button>)}</div>
    <div className="rl-departure-custom">
      <label>Date<input id="departure-date" aria-label="Departure date in IST" type="date" value={date} min={now.date||undefined} max={max.date||undefined} onChange={e=>onChange(e.target.value?e.target.value+"T"+(time||"08:30"):"")}/></label>
      <label>Time<input aria-label="Departure time in IST" type="time" value={time} onChange={e=>onChange(e.target.value&&date?date+"T"+e.target.value:"")}/></label>
    </div>
    <small>{value?"Custom departure selected. Search to apply.":"Leave now is selected. Pick a date or time to plan ahead."}</small>
  </div>;
}
