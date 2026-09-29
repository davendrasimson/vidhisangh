import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { DocumentsService } from '@core/services/documents.service';
import { PublicSignatureStep } from '@core/models/documents.models';
import { NotificationService } from '@core/services/notification.service';
import { SignaturePadComponent } from '@shared/signature-pad/signature-pad.component';

@Component({
  selector: 'app-public-sign', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatButtonModule, MatIconModule, SignaturePadComponent],
  template: `
    <main class="sign-page"><section class="sign-card">
      <div class="brand"><span>V</span><div><strong>VidhiSangh</strong><small>Secure electronic signature</small></div></div>
      @if (loading()) { <p class="state">Opening secure request…</p> }
      @else if (step(); as item) {
        <div class="document"><mat-icon>description</mat-icon><div><small>DOCUMENT</small><h1>{{ item.document_title }}</h1><p>{{ item.sender_message }}</p></div></div>
        @if (item.status !== 'pending') { <div class="done"><mat-icon>{{ item.status === 'signed' ? 'verified' : 'block' }}</mat-icon><h2>This request is {{ item.status }}.</h2></div> }
        @else if (!session()) {
          <div class="verify"><h2>Verify your email</h2><p>A six-digit code will be sent to the email address selected by the sender.</p>
            @if (!otpSent()) { <button mat-flat-button color="primary" (click)="sendOtp()">Send verification code</button> }
            @else { <label>Verification code<input class="vs-input" maxlength="6" inputmode="numeric" [(ngModel)]="otp" /></label><button mat-flat-button color="primary" [disabled]="otp.length !== 6" (click)="verify()">Verify and review</button><button mat-button (click)="sendOtp()">Resend code</button> }
          </div>
        } @else {
          <div class="review"><div class="review-head"><h2>Review and sign</h2><button mat-stroked-button (click)="download()"><mat-icon>download</mat-icon>Download document</button></div>
            <label>Full legal name<input class="vs-input" [(ngModel)]="signedName" /></label><label>Designation (optional)<input class="vs-input" [(ngModel)]="designation" /></label>
            <label>Draw your signature<app-signature-pad (signatureChange)="signature.set($event)" /></label>
            <label class="consent"><input type="checkbox" [(ngModel)]="consent" /> I have reviewed the document and consent to apply my electronic signature.</label>
            <label>Remarks (optional)<textarea class="vs-input" rows="2" [(ngModel)]="remarks"></textarea></label>
            <div class="actions"><button mat-button class="reject" (click)="reject()">Reject</button><button mat-flat-button color="primary" [disabled]="!canSign()" (click)="sign()"><mat-icon>draw</mat-icon>Sign document</button></div>
          </div>
        }
      } @else { <p class="state">This signing link is invalid or has expired.</p> }
      <footer>Identity verification and signing events are recorded in the document audit trail.</footer>
    </section></main>`,
  styles: [`:host{display:block;min-height:100vh;background:linear-gradient(145deg,#f6f1e8,#fff)}.sign-page{max-width:760px;margin:auto;padding:32px 16px}.sign-card{padding:28px;border:1px solid #ded6c8;border-radius:18px;background:#fff;box-shadow:0 18px 50px #3a2e1a18}.brand{display:flex;align-items:center;gap:10px;padding-bottom:20px;border-bottom:1px solid #eee}.brand>span{display:grid;place-items:center;width:40px;height:40px;border-radius:11px;background:#bd7b20;color:#fff;font:700 22px Georgia}.brand div{display:grid}.brand small,.document small{color:#786d5e}.document{display:flex;gap:14px;padding:24px 0}.document mat-icon{color:#bd7b20}.document h1{margin:3px 0;font:700 25px Georgia}.document p,.verify p{color:#6b6257}.verify,.review{display:grid;gap:14px;padding:20px;border-radius:14px;background:#faf8f4}.verify h2,.review h2{margin:0}.verify label,.review label{display:grid;gap:6px;font-size:13px;font-weight:600}.verify input{max-width:220px;font-size:22px;letter-spacing:.3em}.review-head,.actions{display:flex;justify-content:space-between;align-items:center;gap:12px}.consent{display:flex!important;grid-template-columns:auto 1fr;align-items:flex-start}.consent input{margin-top:3px}.actions{justify-content:flex-end}.reject{color:#a12828}.done,.state{text-align:center;padding:45px 12px}.done mat-icon{font-size:42px;width:42px;height:42px;color:#287a4c}footer{margin-top:24px;color:#84796b;font-size:11px;text-align:center}@media(max-width:600px){.sign-card{padding:18px}.review-head{align-items:stretch;flex-direction:column}.review-head button{align-self:flex-start}}`],
})
export class PublicSignComponent {
  private readonly docs = inject(DocumentsService); private readonly notify = inject(NotificationService);
  private readonly token = inject(ActivatedRoute).snapshot.paramMap.get('token') ?? '';
  protected readonly loading = signal(true); protected readonly step = signal<PublicSignatureStep | null>(null);
  protected readonly session = signal(''); protected readonly otpSent = signal(false); protected readonly signature = signal('');
  protected otp = ''; protected signedName = ''; protected designation = ''; protected remarks = ''; protected consent = false;
  constructor() { void this.load(); }
  private async load(): Promise<void> { try { const item = await firstValueFrom(this.docs.publicSignature(this.token)); this.step.set(item); this.signedName = item.signer_name; this.designation = item.designation ?? ''; } catch { /* interceptor */ } finally { this.loading.set(false); } }
  protected async sendOtp(): Promise<void> { try { await firstValueFrom(this.docs.sendSigningOtp(this.token)); this.otpSent.set(true); this.notify.success('Verification code sent.'); } catch { /* handled */ } }
  protected async verify(): Promise<void> { try { const result = await firstValueFrom(this.docs.verifySigningOtp(this.token, this.otp)); this.session.set(result.session_token); } catch { /* handled */ } }
  protected canSign(): boolean { return this.signedName.trim().length > 1 && !!this.signature() && this.consent; }
  protected async download(): Promise<void> { try { this.save(await firstValueFrom(this.docs.publicSigningDocument(this.token, this.session())), this.step()?.document_title ?? 'document'); } catch { /* handled */ } }
  protected async sign(): Promise<void> { if (!this.canSign()) return; try { this.step.set(await firstValueFrom(this.docs.publicSign(this.token, this.session(), { signed_name: this.signedName, designation: this.designation, signature_data: this.signature(), remarks: this.remarks, consent: this.consent }))); this.notify.success('Document signed successfully.'); } catch { /* handled */ } }
  protected async reject(): Promise<void> { const reason = window.prompt('Reason for rejecting this document:')?.trim(); if (!reason) return; try { this.step.set(await firstValueFrom(this.docs.publicReject(this.token, this.session(), reason))); } catch { /* handled */ } }
  private save(blob: Blob, name: string): void { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url); }
}
