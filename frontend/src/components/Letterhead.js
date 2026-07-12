import React from "react";
import { Stethoscope, MapPin, Phone, Mail } from "lucide-react";

export const Letterhead = ({ settings }) => {
  if (!settings) return null;
  return (
    <div className="border-b-2 border-moneygreen-600 pb-4 mb-6" data-testid="form-letterhead">
      <div className="flex items-center gap-4">
        {settings.logo ? (
          <img src={settings.logo} alt="logo" className="h-14 w-14 object-contain rounded-md" data-testid="letterhead-logo" />
        ) : (
          <div className="h-14 w-14 rounded-md bg-moneygreen-600 flex items-center justify-center shrink-0">
            <Stethoscope className="w-7 h-7 text-white" />
          </div>
        )}
        <div className="min-w-0">
          <h2 className="font-heading text-xl sm:text-2xl font-extrabold text-moneygreen-800 tracking-tight leading-tight">
            {settings.clinic_name}
          </h2>
          {settings.tagline && <p className="text-sm text-stone-500">{settings.tagline}</p>}
        </div>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-xs text-stone-500">
        {settings.address && <span className="inline-flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{settings.address}</span>}
        {settings.phone && <span className="inline-flex items-center gap-1"><Phone className="w-3.5 h-3.5" />{settings.phone}</span>}
        {settings.email && <span className="inline-flex items-center gap-1"><Mail className="w-3.5 h-3.5" />{settings.email}</span>}
      </div>
    </div>
  );
};
