// app/signup/layout.tsx
// Remove the <html> and <body> tags here. 
// Next.js will automatically use the ones from your root layout.

export default function SignUpLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="signup-container">
      {children}
    </div>
  );
}