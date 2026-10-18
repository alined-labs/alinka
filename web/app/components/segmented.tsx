import { Toggle } from "@base-ui/react/toggle";
import { ToggleGroup } from "@base-ui/react/toggle-group";

/** ak-seg: one pressed option out of a few (Base UI ToggleGroup, arrow keys move between them). */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; icon?: React.ReactNode }[];
  onChange: (value: T) => void;
}) {
  return (
    <ToggleGroup
      aria-label={label}
      value={[value]}
      onValueChange={(v) => {
        const next = v[0] as T | undefined;
        if (next) onChange(next);
      }}
      className="ak-seg"
    >
      {options.map((o) => (
        <Toggle key={o.value} value={o.value} className="inline-flex items-center gap-1.5">
          {o.icon}
          {o.label}
        </Toggle>
      ))}
    </ToggleGroup>
  );
}
