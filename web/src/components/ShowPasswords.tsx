import { useId } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

/**
 * Let somebody read what they are typing into a password box.
 *
 * A password field hides its own contents from the person entering it, which is the right
 * default and the wrong only option: it is why a mistyped password is discovered by being
 * refused rather than by being looked at. On a form that sets a *new* password it does not
 * even protect much — nobody has the password yet for a shoulder to be worth looking over.
 *
 * Not a substitute for a confirmation field where there is one. That catches a typo you did
 * not notice; this lets you check for one you suspect.
 *
 * The id is generated because more than one of these can share a page, and a label bound to
 * a duplicate id is a label that toggles somebody else's checkbox.
 */
export function ShowPasswords({
  showing,
  onChange,
  label = "Show password",
}: {
  showing: boolean;
  onChange: (showing: boolean) => void;
  /** Plural where the form has more than one box. */
  label?: string;
}) {
  const id = useId();

  return (
    <div className="flex items-center gap-3">
      <Checkbox
        id={id}
        checked={showing}
        onCheckedChange={(value) => onChange(value === true)}
      />
      <Label htmlFor={id} className="text-sm font-normal">
        {label}
      </Label>
    </div>
  );
}
