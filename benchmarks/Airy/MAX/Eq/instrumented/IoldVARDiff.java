package demo.benchmarks.Airy.MAX.Eq.instrumented;
import equiv.checking.symbex.UnInterpreted;
public class IoldVARDiff{
    public static double snippet(double a, double b) {
        if (b > a)
            return b;
        else
            return a;
    }
public static void main(String[] args){
IoldVARDiff temp = new IoldVARDiff();
temp.snippet(1,1);
}
}
