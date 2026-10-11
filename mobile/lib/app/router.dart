import 'package:flutter/material.dart';
import '../features/onboarding/screens/welcome_screen.dart';

class VaakSetuRouter {
  static Route<dynamic> generateRoute(RouteSettings settings) {
    switch (settings.name) {
      case '/':
        return MaterialPageRoute(
          builder: (_) => const WelcomeScreen(),
        );

        default:
          return MaterialPageRoute(
            builder: (_) => const WelcomeScreen(),
          );
    }
  }
}