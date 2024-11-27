import { ClientSideRowModelModule } from "@ag-grid-community/client-side-row-model";
import {
  type ColDef,
  type GetRowIdFunc,
  type GetRowIdParams,
  type ValueFormatterFunc,
} from "@ag-grid-community/core";
import { ModuleRegistry } from "@ag-grid-community/core";
import { AgGridReact } from "@ag-grid-community/react";
import "@ag-grid-community/styles/ag-grid.css";
import "@ag-grid-community/styles/ag-theme-quartz.css";
import { AdvancedFilterModule } from "@ag-grid-enterprise/advanced-filter";
import { GridChartsModule } from "@ag-grid-enterprise/charts-enterprise";
import { ColumnsToolPanelModule } from "@ag-grid-enterprise/column-tool-panel";
import { ExcelExportModule } from "@ag-grid-enterprise/excel-export";
import { FiltersToolPanelModule } from "@ag-grid-enterprise/filter-tool-panel";
import { MenuModule } from "@ag-grid-enterprise/menu";
import { RangeSelectionModule } from "@ag-grid-enterprise/range-selection";
import { RichSelectModule } from "@ag-grid-enterprise/rich-select";
import { RowGroupingModule } from "@ag-grid-enterprise/row-grouping";
import { SetFilterModule } from "@ag-grid-enterprise/set-filter";
import { SparklinesModule } from "@ag-grid-enterprise/sparklines";
import { StatusBarModule } from "@ag-grid-enterprise/status-bar";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import styles from "./FinanceExample.module.css";
import { getData } from "./data";

interface Props {
  gridTheme?: string;
  isDarkMode?: boolean;
}

ModuleRegistry.registerModules([
  ClientSideRowModelModule,
  AdvancedFilterModule,
  ColumnsToolPanelModule,
  ExcelExportModule,
  FiltersToolPanelModule,
  GridChartsModule,
  MenuModule,
  RangeSelectionModule,
  RowGroupingModule,
  SetFilterModule,
  RichSelectModule,
  StatusBarModule,
  SparklinesModule,
]);

const numberFormatter: ValueFormatterFunc = ({ value }) => {
  const formatter = new Intl.NumberFormat("en-US", {
    style: "decimal",
    maximumFractionDigits: 2,
  });
  return value == null ? "" : formatter.format(value);
};

export const FinanceExample: React.FC<Props> = ({
  gridTheme = "ag-theme-quartz",
  isDarkMode = false,
}) => {
  const [rowData, setRowData] = useState(() => getData());
  const gridRef = useRef<AgGridReact>(null);
  let socket: WebSocket;
  // 在组件挂载时建立 WebSocket 连接
  useEffect(() => {
    // 创建 WebSocket 连接
    socket = new WebSocket("ws://localhost:8000/ws");
    console.log("WebSocket created");

    // 连接打开事件
    socket.onopen = () => {
      console.log("WebSocket connected");
    };

    // 接收消息事件
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data)

      setRowData((rowData) =>
      {
        console.log(rowData.length)

        return rowData.map((item) => {
          console.log(item.InstrumentID)
          // 当price为最大值时，过滤


          return {
          ...item,
          LastPrice: data[item.InstrumentID].LastPrice,
          PreSettlementPrice: data[item.InstrumentID].PreSettlementPrice,
          PreClosePrice: data[item.InstrumentID].PreClosePrice,
          PreOpenInterest: data[item.InstrumentID].PreOpenInterest,
          Volume: data[item.InstrumentID].Volume,
          Turnover: data[item.InstrumentID].Turnover,
          OpenInterest: data[item.InstrumentID].OpenInterest,
          ClosePrice: data[item.InstrumentID].ClosePrice,
          SettlementPrice: data[item.InstrumentID].SettlementPrice,
          UpperLimitPrice: data[item.InstrumentID].UpperLimitPrice,
          LowerLimitPrice: data[item.InstrumentID].LowerLimitPrice,
          UpdateTime: data[item.InstrumentID].UpdateTime,
          UpdateMillisec: data[item.InstrumentID].UpdateMillisec,
          BidPrice1: data[item.InstrumentID].BidPrice1,
          BidVolume1: data[item.InstrumentID].BidVolume1,
          AskPrice1: data[item.InstrumentID].AskPrice1,
          AskVolume1: data[item.InstrumentID].AskVolume1,
          }
        }) });
    };

    // 连接关闭事件
    socket.onclose = () => {
      console.log("WebSocket disconnected");
    };

    // 错误事件
    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
    window.addEventListener("beforeunload", () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "Page is being refreshed or closed");
      }
    });
    // 组件卸载时关闭 WebSocket
    return () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "Component unmounted");
      }
    }
  }, []); // 只在组件挂载时执行一次

  const colDefs = useMemo<ColDef[]>(
    () => [
      {
        headerName: "Instrument",
        field: "InstrumentID",
        cellRenderer: "text",
        type: "rightAligned",
        maxWidth: 150,
      },
      {
        headerName: "LastPrice",
        field: "LastPrice",
        cellDataType: "number",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "PreSettlementPrice",
        field: "PreSettlementPrice",
        cellDataType: "number",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "PreClosePrice",
        field: "PreClosePrice",
        cellDataType: "number",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "Volume",
        field: "Volume",
        cellDataType: "number",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "Turnover",
        field: "Turnover",
        cellDataType: "number",
        cellRenderer: "agAnimateShowChangeCellRenderer",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 300,
      },
      {
        headerName: "BidPrice1",
        field: "BidPrice1",
        cellDataType: "number",
        cellRenderer: "agAnimateShowChangeCellRenderer",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "BidVolume1",
        field: "BidVolume1",
        cellDataType: "number",
        cellRenderer: "agAnimateShowChangeCellRenderer",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "AskPrice1",
        field: "AskPrice1",
        cellDataType: "number",
        cellRenderer: "agAnimateShowChangeCellRenderer",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "AskVolume1",
        field: "AskVolume1",
        cellDataType: "number",
        cellRenderer: "agAnimateShowChangeCellRenderer",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
      {
        headerName: "UpdateTime",
        field: "UpdateTime",
        cellDataType: "text",
        type: "rightAligned",
        maxWidth: 150,
      },
      {
        headerName: "UpdateMillisec",
        field: "UpdateMillisec",
        cellDataType: "number",
        type: "rightAligned",
        valueFormatter: numberFormatter,
        maxWidth: 150,
      },
    ],
    []
  );

  const defaultColDef: ColDef = useMemo(
    () => ({
      flex: 1,
      filter: true,
      enableRowGroup: true,
      enableValue: true,
    }),
    []
  );

  const getRowId = useCallback<GetRowIdFunc>(
    ({ data: { ticker } }: GetRowIdParams) => ticker,
    []
  );

  const statusBar = useMemo(
    () => ({
      statusPanels: [
        { statusPanel: "agTotalAndFilteredRowCountComponent" },
        { statusPanel: "agTotalRowCountComponent" },
        { statusPanel: "agFilteredRowCountComponent" },
        { statusPanel: "agSelectedRowCountComponent" },
        { statusPanel: "agAggregationComponent" },
      ],
    }),
    []
  );

  const themeClass = `${gridTheme}${isDarkMode ? "-dark" : ""}`;

  return (
    <div className={styles.wrapper}>
      <div className={styles.container}>
        <div className={`${themeClass} ${styles.grid}`}>
          <AgGridReact
            ref={gridRef}
            getRowId={getRowId}
            rowData={rowData}
            columnDefs={colDefs}
            defaultColDef={defaultColDef}
            enableRangeSelection
            enableCharts
            rowSelection={"multiple"}
            rowGroupPanelShow={"always"}
            suppressAggFuncInHeader
            groupDefaultExpanded={-1}
            statusBar={statusBar}
          />
        </div>
      </div>
    </div>
  );
};
