import { AfterViewInit, Component, ElementRef, EventEmitter, Output, ViewChild } from '@angular/core';

@Component({
  selector: 'app-signature-pad',
  standalone: true,
  template: `<div class="pad"><canvas #canvas (pointerdown)="start($event)" (pointermove)="move($event)" (pointerup)="stop()" (pointerleave)="stop()"></canvas><button type="button" (click)="clear()">Clear signature</button></div>`,
  styles: [`.pad{display:grid;gap:.45rem}.pad canvas{width:100%;height:160px;border:1px dashed rgb(var(--vs-border));border-radius:10px;background:#fff;touch-action:none}.pad button{justify-self:end;color:rgb(var(--vs-brand));font-size:.78rem}`],
})
export class SignaturePadComponent implements AfterViewInit {
  @ViewChild('canvas', { static: true }) canvasRef!: ElementRef<HTMLCanvasElement>;
  @Output() signatureChange = new EventEmitter<string>();
  private drawing = false;
  private context!: CanvasRenderingContext2D;

  ngAfterViewInit(): void {
    const canvas = this.canvasRef.nativeElement;
    canvas.width = Math.max(600, canvas.clientWidth * 2); canvas.height = 320;
    this.context = canvas.getContext('2d')!; this.context.scale(2, 2);
    this.context.lineWidth = 2; this.context.lineCap = 'round'; this.context.strokeStyle = '#172033';
  }
  start(event: PointerEvent): void { this.drawing = true; const p = this.point(event); this.context.beginPath(); this.context.moveTo(p.x, p.y); }
  move(event: PointerEvent): void { if (!this.drawing) return; const p = this.point(event); this.context.lineTo(p.x, p.y); this.context.stroke(); }
  stop(): void { if (!this.drawing) return; this.drawing = false; this.signatureChange.emit(this.canvasRef.nativeElement.toDataURL('image/png')); }
  clear(): void { const c = this.canvasRef.nativeElement; this.context.clearRect(0, 0, c.width, c.height); this.signatureChange.emit(''); }
  private point(event: PointerEvent): { x: number; y: number } { const rect = this.canvasRef.nativeElement.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; }
}
