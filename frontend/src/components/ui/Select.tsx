// 다크 테마에 맞춘 공용 Select — 네이티브 select 대신 커스텀 listbox(키보드 접근성 지원).
"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  /** 트리거 버튼에 추가할 클래스(주로 너비·마진 조정용). */
  className?: string;
  /** 시각적 라벨이 없을 때의 접근성 라벨. */
  "aria-label"?: string;
  id?: string;
}

// 트리거·팝업·옵션 공통 스타일 — 앱 다크 팔레트(#1a1f2e 계열)에 맞춤.
const triggerCls =
  "w-full flex items-center justify-between gap-2 rounded-xl border px-3 py-2.5 text-left text-sm transition-colors " +
  "border-line bg-white dark:bg-[#1a1f2e] " +
  "text-ink " +
  "focus:outline-none focus:ring-2 focus:ring-[#3182F6] " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const popupCls =
  "absolute left-0 right-0 z-50 mt-1 max-h-60 overflow-auto rounded-xl border py-1 shadow-lg " +
  "border-line bg-white dark:bg-[#1a1f2e]";

export function Select({
  value,
  onChange,
  options,
  placeholder = "선택하세요",
  disabled = false,
  className = "",
  id,
  "aria-label": ariaLabel,
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const autoId = useId();
  const listboxId = `${id ?? autoId}-listbox`;

  const selected = options.find((o) => o.value === value);

  // 활성 인덱스를 이동 가능한(비활성 아님) 다음/이전 옵션으로 옮긴다.
  const moveActive = useCallback(
    (from: number, dir: 1 | -1) => {
      const n = options.length;
      if (n === 0) return;
      let i = from;
      for (let step = 0; step < n; step++) {
        i = (i + dir + n) % n;
        if (!options[i]?.disabled) {
          setActiveIdx(i);
          return;
        }
      }
    },
    [options]
  );

  const openMenu = useCallback(() => {
    if (disabled) return;
    setOpen(true);
    const cur = options.findIndex((o) => o.value === value);
    if (cur >= 0 && !options[cur]?.disabled) setActiveIdx(cur);
    else moveActive(-1, 1);
  }, [disabled, moveActive, options, value]);

  const closeMenu = useCallback(() => {
    setOpen(false);
    setActiveIdx(-1);
  }, []);

  const choose = useCallback(
    (opt: SelectOption | undefined) => {
      if (!opt || opt.disabled) return;
      onChange(opt.value);
      closeMenu();
    },
    [onChange, closeMenu]
  );

  // 바깥 클릭 시 닫기.
  useEffect(() => {
    if (!open) return;
    const onDocPointer = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        closeMenu();
      }
    };
    document.addEventListener("pointerdown", onDocPointer);
    return () => document.removeEventListener("pointerdown", onDocPointer);
  }, [open, closeMenu]);

  // 활성 옵션이 보이도록 스크롤.
  useEffect(() => {
    if (!open || activeIdx < 0 || !listRef.current) return;
    const el = listRef.current.children[activeIdx] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [open, activeIdx]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openMenu();
        else moveActive(activeIdx, 1);
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!open) openMenu();
        else moveActive(activeIdx, -1);
        break;
      case "Home":
        if (open) {
          e.preventDefault();
          moveActive(-1, 1);
        }
        break;
      case "End":
        if (open) {
          e.preventDefault();
          moveActive(options.length, -1);
        }
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (!open) openMenu();
        else choose(options[activeIdx]);
        break;
      case "Escape":
        if (open) {
          e.preventDefault();
          closeMenu();
        }
        break;
      case "Tab":
        if (open) closeMenu();
        break;
    }
  };

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={onKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-label={ariaLabel}
        className={triggerCls}
      >
        <span
          className={`truncate ${
            selected
              ? ""
              : "text-ink-muted"
          }`}
        >
          {selected ? selected.label : placeholder}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-[#8B95A1] transition-transform ${
            open ? "rotate-180" : ""
          }`}
          viewBox="0 0 20 20"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M6 8l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel}
          className={popupCls}
        >
          {options.map((opt, i) => {
            const isSelected = opt.value === value;
            const isActive = i === activeIdx;
            return (
              <li
                key={opt.value || `__opt_${i}`}
                role="option"
                aria-selected={isSelected}
                aria-disabled={opt.disabled}
                onMouseEnter={() => !opt.disabled && setActiveIdx(i)}
                onClick={() => choose(opt)}
                className={`flex items-center justify-between gap-2 px-3 py-2 text-sm ${
                  opt.disabled
                    ? "cursor-not-allowed opacity-40"
                    : "cursor-pointer"
                } ${
                  isActive && !opt.disabled
                    ? "bg-surface-1"
                    : ""
                } ${
                  isSelected
                    ? "font-medium text-[#3182F6]"
                    : "text-ink"
                }`}
              >
                <span className="truncate">{opt.label}</span>
                {isSelected && (
                  <svg
                    className="h-4 w-4 shrink-0"
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M5 10l3 3 7-7"
                      stroke="currentColor"
                      strokeWidth="1.75"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default Select;
