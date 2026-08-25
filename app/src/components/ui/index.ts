// Barrel for the EmeHub UI primitives. Wave-2 screens import from here:
//   import { GlassCard, Button, StatusPill } from "@/components/ui";

export { Accordion, AccordionItem } from "./Accordion";
export type { AccordionProps, AccordionItemProps } from "./Accordion";

export { Button } from "./Button";
export type { ButtonProps, ButtonSize, ButtonVariant } from "./Button";

export { Dropdown } from "./Dropdown";
export type { DropdownItem, DropdownProps } from "./Dropdown";

export { GlassCard } from "./GlassCard";
export type { GlassCardProps } from "./GlassCard";

export { Glyph } from "./Glyph";
export type { GlyphFill, GlyphProps } from "./Glyph";

export { ClaudeMark, Icon, ICON_PATHS, Spinner } from "./Icon";
export type { IconName, IconProps, SpinnerSpeed } from "./Icon";

export { Input } from "./Input";
export type { InputProps } from "./Input";

export { Modal } from "./Modal";
export type { ModalProps } from "./Modal";

export { Pill } from "./Pill";
export type { PillProps, PillTone } from "./Pill";

export { Radio, RadioGroup } from "./Radio";
export type { RadioProps, RadioGroupProps } from "./Radio";

export { Range } from "./Range";
export type { RangeProps } from "./Range";

export { SaveBar } from "./SaveBar";

export { Segmented } from "./Segmented";
export type { SegmentedOption, SegmentedProps } from "./Segmented";

export { EmptyState, ErrorState, LoadingState, Notice } from "./States";
export type {
  EmptyStateProps,
  ErrorStateProps,
  LoadingStateProps,
  NoticeProps,
  NoticeTone,
} from "./States";

export { STATUS_TONE, StatusPill, statusTone } from "./StatusPill";
export type { StatusName, StatusPillProps } from "./StatusPill";

export {
  ActivityRowsSkeleton,
  KpiTilesSkeleton,
  PanelHeadingSkeleton,
  ProductCardsSkeleton,
  Skeleton,
  SkeletonRegion,
  SummaryPanelSkeleton,
  TableRowsSkeleton,
} from "./Skeleton";
export type { SkeletonProps } from "./Skeleton";

export {
  Table,
  TableCell,
  TableEmpty,
  TableFootnote,
  TablePager,
  TableRow,
} from "./Table";
export type {
  TableCellProps,
  TableEmptyProps,
  TableProps,
  TableRowProps,
} from "./Table";

export { ToastHost, toast, useToast } from "./Toast";
export type { Toast, ToastKind } from "./Toast";

export { Toggle } from "./Toggle";
export type { ToggleProps } from "./Toggle";
