// 14테마 × 라이트/다크 갤러리 — 프리미티브(카드·StatCard·버튼·배지·폼·차트) 위에서 실시간 비교.
'use client';

import {
  useTheme,
  COLOR_THEMES,
  EDITOR_THEMES,
  THEME_LABELS,
  isEditorTheme,
  type DataTheme,
} from '@/components/ThemeProvider';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { StatCard } from '@/components/ui/stat-card';
import { Section } from '@/components/ui/section';
import { EmptyState } from '@/components/ui/empty-state';
import { useChartColors } from '@/components/ui/chart-theme';
import {
  Rocket,
  TrendingUp,
  MousePointerClick,
  ShieldCheck,
  Ban,
  Moon,
  Sun,
  Inbox,
  Sparkles,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

const AREA = [
  { d: '월', v: 22 },
  { d: '화', v: 28 },
  { d: '수', v: 25 },
  { d: '목', v: 34 },
  { d: '금', v: 31 },
  { d: '토', v: 38 },
  { d: '일', v: 42 },
];
const BARS = [
  { name: 'A안', v: 34 },
  { name: 'B안', v: 28 },
  { name: 'C안', v: 41 },
];

export default function ThemesGallery() {
  const { theme, toggle, dataTheme, setDataTheme } = useTheme();
  const c = useChartColors();
  const editorActive = isEditorTheme(dataTheme);

  return (
    <div className='min-h-screen bg-surface-0 pb-20'>
      {/* 스위처 */}
      <div className='sticky top-0 z-20 border-b border-line bg-surface-0/80 backdrop-blur-md'>
        <div className='mx-auto max-w-6xl px-6 py-4'>
          <div className='mb-3 flex items-center justify-between'>
            <div>
              <h1 className='text-lg font-bold text-ink'>테마 갤러리</h1>
              <p className='text-sm text-ink-secondary'>
                14종 프리셋을 프리미티브 위에서 비교. 현재{' '}
                <span className='font-semibold text-primary'>
                  {THEME_LABELS[dataTheme]}
                </span>{' '}
                · {theme === 'dark' ? '다크' : '라이트'}
              </p>
            </div>
            <Button
              variant='outline'
              size='sm'
              onClick={toggle}
              disabled={editorActive}
              title={editorActive ? '에디터 테마는 항상 다크' : ''}
            >
              {theme === 'dark' ? <Sun /> : <Moon />}
              {theme === 'dark' ? '라이트' : '다크'}
            </Button>
          </div>
          <div className='flex flex-wrap gap-2'>
            {COLOR_THEMES.map(t => (
              <ThemeChip
                key={t}
                t={t}
                active={dataTheme === t}
                onClick={() => setDataTheme(t)}
              />
            ))}
            <span className='mx-1 self-center text-line-strong'>|</span>
            {EDITOR_THEMES.map(t => (
              <ThemeChip
                key={t}
                t={t}
                active={dataTheme === t}
                onClick={() => setDataTheme(t)}
              />
            ))}
          </div>
        </div>
      </div>

      <div className='mx-auto max-w-6xl space-y-12 px-6 py-10'>
        {/* KPI StatCards */}
        <Section title='KPI 지표 카드' description='label·값·델타·아이콘·스파크라인'>
          <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
            <StatCard
              label='클릭 의향률'
              value='34.2'
              unit='%'
              delta={2.1}
              icon={<MousePointerClick />}
              sparkline={[20, 24, 22, 28, 26, 32, 34]}
            />
            <StatCard
              label='구매의도(평균)'
              value='3.8'
              unit='/5'
              delta={0.3}
              deltaSuffix='점'
              tone='point'
              icon={<TrendingUp />}
              sparkline={[3.1, 3.3, 3.2, 3.5, 3.6, 3.7, 3.8]}
            />
            <StatCard
              label='신뢰도'
              value='4.1'
              unit='/5'
              delta={0}
              icon={<ShieldCheck />}
            />
            <StatCard
              label='거부율'
              value='12.4'
              unit='%'
              delta={1.8}
              invertDelta
              tone='muted'
              icon={<Ban />}
              sparkline={[9, 10, 11, 10, 12, 11, 12.4]}
            />
          </div>
        </Section>

        {/* 버튼 */}
        <Section title='버튼' description='shadcn variants + 브랜드 point'>
          <div className='flex flex-wrap items-center gap-3'>
            <Button>
              <Rocket /> Primary
            </Button>
            <Button variant='secondary'>Secondary</Button>
            <Button variant='outline'>Outline</Button>
            <Button variant='ghost'>Ghost</Button>
            <Button variant='destructive'>Destructive</Button>
            <Button variant='link'>Link</Button>
            <Button className='bg-point text-point-foreground hover:bg-point-hover'>
              <Sparkles /> Point
            </Button>
            <Button size='sm'>Small</Button>
            <Button size='lg'>Large</Button>
          </div>
        </Section>

        {/* 배지 + semantic */}
        <Section title='배지 · Semantic' description='상태 색 4종'>
          <div className='flex flex-wrap gap-2'>
            <Badge>Default</Badge>
            <Badge variant='secondary'>Secondary</Badge>
            <Badge variant='outline'>Outline</Badge>
            <Badge className='border-transparent bg-success-subtle text-success'>
              성공
            </Badge>
            <Badge className='border-transparent bg-warning-subtle text-warning'>
              주의
            </Badge>
            <Badge className='border-transparent bg-danger-subtle text-danger'>
              위험
            </Badge>
            <Badge className='border-transparent bg-info-subtle text-info'>정보</Badge>
            <Badge className='border-transparent bg-point-subtle text-point'>포인트</Badge>
          </div>
        </Section>

        {/* 차트 */}
        <Section title='차트' description='테마 색을 따르는 Recharts 프리셋'>
          <div className='grid gap-4 lg:grid-cols-2'>
            <Card className='p-5'>
              <p className='mb-4 text-sm font-semibold text-ink-secondary'>
                주간 클릭 의향률 추이
              </p>
              <ResponsiveContainer width='100%' height={200}>
                <AreaChart data={AREA} margin={{ left: -20, right: 8, top: 4 }}>
                  <defs>
                    <linearGradient id='g' x1='0' y1='0' x2='0' y2='1'>
                      <stop offset='0%' stopColor={c.primary} stopOpacity={0.3} />
                      <stop offset='100%' stopColor={c.primary} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={c.border} strokeDasharray='3 3' vertical={false} />
                  <XAxis
                    dataKey='d'
                    stroke={c['text-tertiary']}
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: c['surface-2'],
                      border: `1px solid ${c.border}`,
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type='monotone'
                    dataKey='v'
                    stroke={c.primary}
                    strokeWidth={2.5}
                    fill='url(#g)'
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
            <Card className='p-5'>
              <p className='mb-4 text-sm font-semibold text-ink-secondary'>시안별 예측</p>
              <ResponsiveContainer width='100%' height={200}>
                <BarChart data={BARS} margin={{ left: -20, right: 8, top: 4 }}>
                  <CartesianGrid stroke={c.border} strokeDasharray='3 3' vertical={false} />
                  <XAxis
                    dataKey='name'
                    stroke={c['text-tertiary']}
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: c.border, opacity: 0.3 }}
                    contentStyle={{
                      background: c['surface-2'],
                      border: `1px solid ${c.border}`,
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey='v' fill={c.point} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </Section>

        {/* 폼 + 상태 */}
        <Section title='폼 · 상태' description='입력·스위치·진행·탭·로딩·빈 상태'>
          <div className='grid gap-4 lg:grid-cols-2'>
            <Card>
              <CardHeader>
                <CardTitle>폼 컨트롤</CardTitle>
                <CardDescription>토큰 기반 입력 요소</CardDescription>
              </CardHeader>
              <CardContent className='space-y-4'>
                <Input placeholder='캠페인 이름 입력...' />
                <Textarea placeholder='설명을 입력하세요...' />
                <div className='flex items-center justify-between'>
                  <span className='text-sm text-ink-secondary'>자동 리밸런스</span>
                  <Switch />
                </div>
                <div className='space-y-1.5'>
                  <div className='flex justify-between text-xs text-ink-tertiary'>
                    <span>예산 소진</span>
                    <span>68%</span>
                  </div>
                  <Progress value={68} />
                </div>
              </CardContent>
              <CardFooter className='gap-2'>
                <Button className='flex-1'>저장</Button>
                <Button variant='outline' className='flex-1'>
                  취소
                </Button>
              </CardFooter>
            </Card>

            <div className='space-y-4'>
              <Tabs defaultValue='sim'>
                <TabsList>
                  <TabsTrigger value='sim'>시뮬레이션</TabsTrigger>
                  <TabsTrigger value='gen'>생성</TabsTrigger>
                  <TabsTrigger value='manage'>매니지먼트</TabsTrigger>
                </TabsList>
                <TabsContent value='sim'>
                  <Card className='p-4 text-sm text-ink-secondary'>
                    집행 전 AI 가상 소비자 반응 예측.
                  </Card>
                </TabsContent>
                <TabsContent value='gen'>
                  <Card className='p-4 text-sm text-ink-secondary'>
                    개선 시안 3종 자동 생성.
                  </Card>
                </TabsContent>
                <TabsContent value='manage'>
                  <Card className='p-4 text-sm text-ink-secondary'>
                    성과를 단일 창구에서 관리.
                  </Card>
                </TabsContent>
              </Tabs>

              <Card className='space-y-2 p-5'>
                <Skeleton className='h-4 w-2/3' />
                <Skeleton className='h-4 w-1/2' />
                <Skeleton className='h-20 w-full' />
              </Card>

              <EmptyState
                icon={<Inbox />}
                title='아직 시뮬레이션이 없어요'
                description='첫 광고를 업로드하면 가상 소비자 반응을 예측합니다.'
                action={
                  <Button size='sm'>
                    <Rocket /> 새 시뮬레이션
                  </Button>
                }
              />
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}

function ThemeChip({
  t,
  active,
  onClick,
}: {
  t: DataTheme;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      data-theme={t}
      className={
        'group inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ' +
        (active
          ? 'border-primary bg-primary-subtle text-primary'
          : 'border-line bg-surface-2 text-ink-secondary hover:border-line-strong')
      }
    >
      <span className='size-3 rounded-full bg-primary ring-1 ring-inset ring-black/10' />
      {THEME_LABELS[t]}
    </button>
  );
}
