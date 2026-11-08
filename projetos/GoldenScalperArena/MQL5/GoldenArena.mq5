//+------------------------------------------------------------------+
//| Golden Scalper Arena                                             |
//| Phase 1: read-only market snapshot exporter                     |
//| This EA is simulation infrastructure only. It never trades.     |
//+------------------------------------------------------------------+
#property strict
#property version   "001.000"
#property description "Golden Scalper Arena - read-only snapshot exporter"

input string InpExportDirectory = "GoldenScalperArena";
input string InpRunId            = "";
input int    InpMinimumTickGapMs = 0;

ulong  g_event_index = 0;
ulong  g_last_export_msc = 0;
string g_run_id = "";

string TickFileName()
  {
   return InpExportDirectory + "\\ticks.csv";
  }

string SpecFileName()
  {
   return InpExportDirectory + "\\symbol_spec.csv";
  }

int OpenAppend(const string file_name)
  {
   int handle = FileOpen(file_name,
                         FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON |
                         FILE_SHARE_READ | FILE_SHARE_WRITE, ',');
   if(handle == INVALID_HANDLE)
     {
      PrintFormat("GoldenArena: export disabled for %s, error=%d", file_name, GetLastError());
      return INVALID_HANDLE;
     }
   FileSeek(handle, 0, SEEK_END);
   return handle;
  }

void WriteSymbolSpec()
  {
   int handle = OpenAppend(SpecFileName());
   if(handle == INVALID_HANDLE)
      return;
   if(FileSize(handle) == 0)
      FileWrite(handle, "run_id", "symbol", "digits", "point", "tick_size",
                "tick_value", "contract_size", "volume_min", "volume_max",
                "volume_step", "currency_base", "currency_quote");
   FileWrite(handle, g_run_id, _Symbol,
             IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS)),
             DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_POINT), 10),
             DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE), 10),
             DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), 10),
             DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE), 4),
             DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 4),
             DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX), 4),
             DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), 4),
             SymbolInfoString(_Symbol, SYMBOL_CURRENCY_BASE),
             SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT));
   FileFlush(handle);
   FileClose(handle);
  }

bool LatestClosedBar(const ENUM_TIMEFRAMES timeframe, MqlRates &bar)
  {
   MqlRates rows[];
   ArraySetAsSeries(rows, true);
   int copied = CopyRates(_Symbol, timeframe, 1, 1, rows);
   if(copied != 1)
      return false;
   bar = rows[0];
   return true;
  }

void ExportTick(const MqlTick &tick)
  {
   if(InpMinimumTickGapMs > 0 && g_last_export_msc > 0 &&
      tick.time_msc > 0 && tick.time_msc - g_last_export_msc < (ulong)InpMinimumTickGapMs)
      return;

   MqlRates m1, m5, m15, h1;
   bool has_m1 = LatestClosedBar(PERIOD_M1, m1);
   bool has_m5 = LatestClosedBar(PERIOD_M5, m5);
   bool has_m15 = LatestClosedBar(PERIOD_M15, m15);
   bool has_h1 = LatestClosedBar(PERIOD_H1, h1);

   int handle = OpenAppend(TickFileName());
   if(handle == INVALID_HANDLE)
      return;
   if(FileSize(handle) == 0)
      FileWrite(handle, "run_id", "event_index", "timestamp", "symbol", "bid", "ask", "spread",
                "m1_available", "m1_time", "m1_open", "m1_high", "m1_low", "m1_close", "m1_tick_volume",
                "m5_available", "m5_time", "m5_open", "m5_high", "m5_low", "m5_close", "m5_tick_volume",
                "m15_available", "m15_time", "m15_open", "m15_high", "m15_low", "m15_close", "m15_tick_volume",
                "h1_available", "h1_time", "h1_open", "h1_high", "h1_low", "h1_close", "h1_tick_volume");
   FileWrite(handle, g_run_id, IntegerToString((long)g_event_index),
             TimeToString((datetime)tick.time, TIME_DATE | TIME_SECONDS), _Symbol,
             DoubleToString(tick.bid, _Digits), DoubleToString(tick.ask, _Digits),
             DoubleToString(tick.ask - tick.bid, _Digits),
             has_m1 ? "1" : "",
             has_m1 ? IntegerToString((long)m1.time) : "",
             has_m1 ? DoubleToString(m1.open, _Digits) : "",
             has_m1 ? DoubleToString(m1.high, _Digits) : "",
             has_m1 ? DoubleToString(m1.low, _Digits) : "",
             has_m1 ? DoubleToString(m1.close, _Digits) : "",
             has_m1 ? IntegerToString((long)m1.tick_volume) : "",
             has_m5 ? "1" : "",
             has_m5 ? IntegerToString((long)m5.time) : "",
             has_m5 ? DoubleToString(m5.open, _Digits) : "",
             has_m5 ? DoubleToString(m5.high, _Digits) : "",
             has_m5 ? DoubleToString(m5.low, _Digits) : "",
             has_m5 ? DoubleToString(m5.close, _Digits) : "",
             has_m5 ? IntegerToString((long)m5.tick_volume) : "",
             has_m15 ? "1" : "",
             has_m15 ? IntegerToString((long)m15.time) : "",
             has_m15 ? DoubleToString(m15.open, _Digits) : "",
             has_m15 ? DoubleToString(m15.high, _Digits) : "",
             has_m15 ? DoubleToString(m15.low, _Digits) : "",
             has_m15 ? DoubleToString(m15.close, _Digits) : "",
             has_m15 ? IntegerToString((long)m15.tick_volume) : "",
             has_h1 ? "1" : "",
             has_h1 ? IntegerToString((long)h1.time) : "",
             has_h1 ? DoubleToString(h1.open, _Digits) : "",
             has_h1 ? DoubleToString(h1.high, _Digits) : "",
             has_h1 ? DoubleToString(h1.low, _Digits) : "",
             has_h1 ? DoubleToString(h1.close, _Digits) : "",
             has_h1 ? IntegerToString((long)h1.tick_volume) : "");
   FileFlush(handle);
   FileClose(handle);
   g_event_index++;
   g_last_export_msc = tick.time_msc;
  }

int OnInit()
  {
   g_run_id = InpRunId;
   if(StringLen(g_run_id) == 0)
      g_run_id = _Symbol + "-" + IntegerToString((int)GetTickCount());
   if(!SymbolSelect(_Symbol, true))
      return INIT_FAILED;
   WriteSymbolSpec();
   PrintFormat("GoldenArena read-only exporter ready: run_id=%s symbol=%s", g_run_id, _Symbol);
   return INIT_SUCCEEDED;
  }

void OnTick()
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;
   ExportTick(tick);
  }

void OnDeinit(const int reason)
  {
   PrintFormat("GoldenArena read-only exporter stopped: run_id=%s events=%I64u reason=%d",
               g_run_id, g_event_index, reason);
  }


