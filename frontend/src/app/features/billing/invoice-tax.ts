import { InvoiceTaxFields } from '@core/models/billing.models';

/** GST lines for the totals box: CGST + SGST within our state, IGST across states. */
export function taxRows(inv: InvoiceTaxFields & { tax_rate: string | number; tax_amount: string | number }): { label: string; amount: string | number }[] {
  const rate = Number(inv.tax_rate);
  const split = inv.tax_split;
  if (split?.igst !== undefined) return [{ label: `IGST (${rate}%)`, amount: split.igst }];
  if (split?.cgst !== undefined && split.sgst !== undefined) {
    return [{ label: `CGST (${rate / 2}%)`, amount: split.cgst }, { label: `SGST (${rate / 2}%)`, amount: split.sgst }];
  }
  return [{ label: `GST (${rate}%)`, amount: inv.tax_amount }];
}
