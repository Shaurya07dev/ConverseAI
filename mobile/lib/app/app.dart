import 'package:flutter/material.dart';

import 'theme.dart';
import 'router.dart';

class VaakSetuApp extends StatelessWidget {
  const VaakSetuApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VaakSetu',
      debugShownCheckedModeBanner: false,
      theme: VaakSetuTheme.dark(),
      initialRoute: '/',
      onGenerateRoute: VaakSetuRouter.generateRoute,
    );
  }
}