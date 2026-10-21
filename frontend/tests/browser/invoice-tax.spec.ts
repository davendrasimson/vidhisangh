import { expect, test } from '@playwright/test';

const BRANDING = { template_id: 'classic', legal_name: 'Rao Chambers', address: 'Delhi', email: '', phone: '', gstin: '07AAAFT1234K1Z5',
  pan: '', logo_url: '', accent_color: '#215dcc', bank_details: '', payment_terms: '', footer: 'System generated.', signature_name: '',
  proforma_prefix: 'PF', invoice_prefix: 'INV', credit_note_prefix: 'CN', receipt_prefix: 'RCT' };
const BASE = { invoice_number: 'INV-0001', document_type: 'tax_invoice', client_name: 'Bombay Mills Ltd', status: 'sent',
  issue_date: '2026-10-22', due_date: null, currency: 'INR', subtotal: '10000.00', tax_rate: '18.00', tax_amount: '1800.00',
  total: '11800.00', amount_paid: '0.00', notes: null, verification_code: 'ABC', branding: BRANDING,
  line_items: [{ id: 'l', description: 'Opinion', quantity: '1', unit_price: '10000.00', amount: '10000.00' }] };

test('an inter-state invoice shows IGST, the client GSTIN, place of supply and expected TDS', async ({ page }) => {
  await page.route('**/api/v1/billing/public/invoices/t1', r => r.fulfill({ json: {
    ...BASE, client_gstin: '27AAACB1234K1Z9', place_of_supply: '27 – Maharashtra', tax_split: { igst: '1800.00' },
    reverse_charge: false, tds_section: '194J', tds_rate: '10.00', tds_amount: '1000.00' } }));
  await page.goto('/pay/t1');
  await expect(page.getByText('GSTIN: 27AAACB1234K1Z9')).toBeVisible();
  await expect(page.getByText('Place of supply: 27 – Maharashtra')).toBeVisible();
  await expect(page.getByText('IGST (18%)')).toBeVisible();
  await expect(page.getByText('TDS u/s 194J @ 10.00%: ₹1,000.00')).toBeVisible();
  await expect(page.getByText('Tax payable on reverse charge')).toHaveCount(0);
});

test('a reverse-charge invoice says so; within the state GST splits into CGST and SGST', async ({ page }) => {
  await page.route('**/api/v1/billing/public/invoices/t2', r => r.fulfill({ json: {
    ...BASE, tax_rate: '0.00', tax_amount: '0.00', total: '10000.00', reverse_charge: true, tax_split: null } }));
  await page.route('**/api/v1/billing/public/invoices/t3', r => r.fulfill({ json: {
    ...BASE, tax_split: { cgst: '900.00', sgst: '900.00' }, place_of_supply: '07 – Delhi' } }));
  await page.goto('/pay/t2');
  await expect(page.getByText(/Tax payable on reverse charge:\s*Yes/)).toBeVisible();
  await page.goto('/pay/t3');
  await expect(page.getByText('CGST (9%)')).toBeVisible();
  await expect(page.getByText('SGST (9%)')).toBeVisible();
});
