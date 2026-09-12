/**
 * DEV-ONLY VERIFICATION SHIM — delete this file once you've run a real
 * `npm install` (which brings real @types/react / @types/react-dom).
 *
 * This exists because the code in this repo was authored in a sandbox with
 * no network access, so the real type packages couldn't be installed to
 * verify against. It declares just enough of the React API surface that's
 * actually used in this codebase so `tsc --noEmit` / `npm run typecheck`
 * catches real mistakes (wrong prop names, missing required props, bad
 * return types) during authoring — it is intentionally not a complete or
 * accurate model of React's real types, and TypeScript will silently accept
 * things the real @types/react would reject. Once real types are installed,
 * this file becomes redundant (and TS will start erroring on the duplicate
 * module declarations) — delete it at that point.
 */

declare module "react" {
  export type ReactNode = any;
  export type ReactElement = any;
  export type PropsWithChildren<P = unknown> = P & { children?: ReactNode };
  export interface FC<P = Record<string, never>> {
    (props: PropsWithChildren<P>): ReactElement | null;
  }

  export type Dispatch<A> = (value: A) => void;
  export type SetStateAction<S> = S | ((prev: S) => S);

  export function useState<S>(
    initial: S | (() => S)
  ): [S, Dispatch<SetStateAction<S>>];
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useCallback<T extends (...args: any[]) => any>(fn: T, deps: readonly unknown[]): T;
  export function useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
  export function useRef<T>(initial: T): { current: T };
  export function useRef<T>(initial: T | null): { current: T | null };
  export function useRef<T = undefined>(): { current: T | undefined };
  export function createContext<T>(defaultValue: T): {
    Provider: FC<{ value: T; children?: ReactNode }>;
    Consumer: FC<{ children: (value: T) => ReactNode }>;
  };
  export function useContext<T>(ctx: { Provider: FC<{ value: T; children?: ReactNode }> }): T;
  export function forwardRef<T, P = Record<string, never>>(
    render: (props: P, ref: { current: T | null }) => ReactElement | null
  ): FC<P & { ref?: { current: T | null } }>;

  export type ButtonHTMLAttributes<T> = Record<string, any>;
  export type HTMLAttributes<T> = Record<string, any>;
  export type InputHTMLAttributes<T> = Record<string, any>;
  export type AnchorHTMLAttributes<T> = Record<string, any>;
  export type ElementRef<T> = any;
  export type ComponentPropsWithoutRef<T> = Record<string, any>;
  export interface ChangeEvent<T = Element> {
    target: T & { value: string; files?: FileList | null };
  }
  export interface KeyboardEvent<T = Element> {
    key: string;
    shiftKey: boolean;
    preventDefault(): void;
    target: T;
  }
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}
declare module "react/jsx-dev-runtime" {
  export const jsxDEV: any;
  export const Fragment: any;
}

declare module "react-dom/client" {
  export function createRoot(container: Element | DocumentFragment): {
    render(children: unknown): void;
  };
}

declare module "react-router-dom" {
  import type { ReactNode } from "react";

  export interface RouteObject {
    path?: string;
    index?: boolean;
    element?: ReactNode;
    children?: RouteObject[];
  }
  export function createBrowserRouter(routes: RouteObject[]): unknown;
  export const RouterProvider: (props: { router: unknown }) => JSX.Element;
  export const Outlet: () => JSX.Element;
  export const NavLink: (props: {
    to: string;
    end?: boolean;
    className?: string | ((state: { isActive: boolean }) => string);
    onClick?: () => void;
    children?: ReactNode;
  }) => JSX.Element;
  export const Link: (props: {
    to: string;
    className?: string;
    onClick?: () => void;
    children?: ReactNode;
  }) => JSX.Element;
  export function useLocation(): { pathname: string };
  export function useNavigate(): (to: string) => void;
}

// Only the react-icons/fi (Feather) subset used in this codebase — real
// react-icons ships full types (checked: $NPM_ROOT/react-icons/index.d.ts
// exists), this just avoids wiring a symlink into this sandbox for one
// subset. Delete alongside the rest of this file once `npm install` runs.
declare module "react-icons/fi" {
  import type { FC } from "react";
  type IconProps = { className?: string; size?: number | string; "aria-hidden"?: boolean };
  export const FiHome: FC<IconProps>;
  export const FiMessageSquare: FC<IconProps>;
  export const FiCheckSquare: FC<IconProps>;
  export const FiSmartphone: FC<IconProps>;
  export const FiDatabase: FC<IconProps>;
  export const FiUser: FC<IconProps>;
  export const FiZap: FC<IconProps>;
  export const FiCpu: FC<IconProps>;
  export const FiActivity: FC<IconProps>;
  export const FiSettings: FC<IconProps>;
  export const FiKey: FC<IconProps>;
  export const FiSun: FC<IconProps>;
  export const FiMoon: FC<IconProps>;
  export const FiClock: FC<IconProps>;
  export const FiMenu: FC<IconProps>;
  export const FiX: FC<IconProps>;
  export const FiImage: FC<IconProps>;
  export const FiMic: FC<IconProps>;
  export const FiSend: FC<IconProps>;
  export const FiRefreshCw: FC<IconProps>;
  export const FiXCircle: FC<IconProps>;
  export const FiTrash2: FC<IconProps>;
  export const FiCheckCircle: FC<IconProps>;
  export const FiAlertTriangle: FC<IconProps>;
  export const FiChevronRight: FC<IconProps>;
  export const FiCheck: FC<IconProps>;
  export const FiSearch: FC<IconProps>;
  export const FiPackage: FC<IconProps>;
  export const FiShield: FC<IconProps>;
  export const FiServer: FC<IconProps>;
  export const FiHardDrive: FC<IconProps>;
  export const FiWifi: FC<IconProps>;
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
  interface Element {}
  // Real @types/react uses this same mechanism (IntrinsicAttributes) to make
  // `key` valid on any JSX element without it needing to be part of the
  // component's own declared props. Without it, `<Item key={x} .../>` in a
  // list would falsely fail type-checking against this shim.
  interface IntrinsicAttributes {
    key?: string | number | bigint | null;
  }
}

// Tailwind/Vite CSS side-effect imports.
declare module "*.css";
